#!/usr/bin/env python3
"""Generate seeded run designs for the two relational localizers (tasks relsem and reldist).

Mirrors ``prepare_sessions.py``: argparse, one seed, design CSVs
under ``output/sourcedata/sub-XX/ses-YY/`` and a diagnostics pass that asserts
every invariant before anything is written.

Design (one subject, one session):

- Three cells. ``rel_near`` and ``rel_far``: choose C's partner under the
  A : B relation, with A : B from a near or a far semantic domain;
  ``sem_far``: choose the option closest in meaning to C (far A : B, shown but
  irrelevant). Task ``relsem`` (relational vs semantic completion) alternates
  ``rel_far`` and ``sem_far`` blocks; task ``reldist`` (relational distance,
  i.e. difficulty) alternates ``rel_near`` and ``rel_far`` blocks.
- A run is 10 s fixation, five blocks, 12 s fixation, five blocks, 14 s
  fixation (296 s; 212 volumes at TR 1.4 s, request 215). A block is a 2 s
  rule cue and four 6 s trials of one cell, so each cell has five blocks and
  20 trials per run. The two cells strictly alternate: of the 252 orders this
  is the most efficient for the run's contrast and keeps it at the highest
  frequency (most robust to drift and high-pass filtering). Half of each
  task's runs start with each cell.
- A trial shows fixation, ``A``, ``A : B``, ``C :``, then ``C :`` with two
  vertically stacked options (``D_rel``, ``D_sem``) for the response window.
- No frame and no displayed word repeats within a session. Near frames are
  ``rel_near``. Within each relation the far frames are split into
  ``reldist`` ``rel_far`` (as many as the relation's near frames) and equal
  ``relsem`` ``rel_far`` and ``sem_far`` sets, so both contrasts are
  relation-matched; seeded draws plus swaps balance the match columns between
  the two cells of each contrast. Each relation's frames are dealt to runs
  identically for both cells of its task, and blocks hold distinct relations.
- Acquisition order alternates tasks (relsem run 1, reldist run 1, ...).
- Upper/lower correct positions are fixed here (two of each per block, at most
  three identical in a row); nothing is randomized at run time.

Usage:
    python prepare_localizer.py --items items.tsv --subject 01 --session 10 --seed 1001
    python prepare_localizer.py --practice-items practice.tsv --subject 01 --session 10 --seed 1001
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import logging
import math
import random
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import gamma

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timing (seconds) and run structure
# ---------------------------------------------------------------------------

TR = 1.4
SCREENS = ("fixation", "word_a", "pair", "word_c", "options", "post")
SCREEN_DURATIONS = {"fixation": 0.25, "word_a": 0.50, "pair": 1.25, "word_c": 0.50, "options": 3.00, "post": 0.50}
CUE_DURATION = 2.0
LEAD_FIXATION, MID_FIXATION, END_FIXATION = 10.0, 12.0, 14.0
TRIALS_PER_BLOCK = 4
BLOCKS_PER_CELL = 5
N_VOLUMES = 215
TASKS = {"relsem": ("rel_far", "sem_far"), "reldist": ("rel_near", "rel_far")}
RULE_OF_CELL = {"rel_near": "rel", "rel_far": "rel", "sem_far": "sem"}
DISTANCE_OF_CELL = {"rel_near": "near", "rel_far": "far", "sem_far": "far"}
MAX_SAME_POSITION_RUN = 3
TASK_SUFFIX = "Korean"
PRACTICE_TASK = "relloc"
PRACTICE_CELLS = ("rel_near", "sem_far", "rel_far", "sem_far", "rel_near", "sem_far", "rel_far", "sem_far")
UPPER, LOWER = 1, 2

# ---------------------------------------------------------------------------
# Efficiency model (identical to the stage-10 analysis in neuroICL)
# ---------------------------------------------------------------------------

HIGH_PASS_HZ = 1.0 / 128.0
AR_RHO = 0.3
OVERSAMPLING = 50
MIN_ONSET = -24.0

INTEGER_COLUMNS = ("run", "acquisition", "block_idx", "trial_idx", "trial_in_block", "correct_option")
ITEM_COLUMNS = ("frame_id", "relation", "category", "c", "d_rel", "d_sem", "a", "b", "distance")
WORD_COLUMNS = ("c", "d_rel", "d_sem", "a", "b")
PRACTICE_COLUMNS = ("frame_id", "relation", "category", "c", "d_rel", "d_sem", "a_near", "b_near", "a_far", "b_far")


def trial_duration(screens: dict[str, float]) -> float:
    """Return the trial length implied by the screen durations."""

    return float(sum(screens[name] for name in SCREENS))


def block_onsets(screens: dict[str, float]) -> tuple[np.ndarray, list[tuple[float, float]], float]:
    """Return the block onsets, the (onset, duration) of each fixation period, and the run length."""

    block_s = CUE_DURATION + TRIALS_PER_BLOCK * trial_duration(screens)
    n_blocks = 2 * BLOCKS_PER_CELL
    blocks, fixations, t = [], [(0.0, LEAD_FIXATION)], LEAD_FIXATION
    for k in range(n_blocks):
        blocks.append(t)
        t += block_s
        if k + 1 == n_blocks // 2:
            fixations.append((t, MID_FIXATION))
            t += MID_FIXATION
    fixations.append((t, END_FIXATION))
    return np.array(blocks), fixations, t + END_FIXATION


# ---------------------------------------------------------------------------
# Design-matrix pieces (nilearn-equivalent: SPM HRF, oversampled boxcars)
# ---------------------------------------------------------------------------


def spm_hrf(tr: float = TR, oversampling: int = OVERSAMPLING, time_length: float = 32.0) -> np.ndarray:
    """Return the SPM canonical HRF on the oversampled grid (nilearn ``spm``)."""

    dt = tr / oversampling
    stamps = np.linspace(0, time_length, int(np.rint(time_length / dt)))
    hrf = gamma.pdf(stamps, 6.0, loc=dt, scale=1.0) - 0.167 * gamma.pdf(stamps, 16.0, loc=dt, scale=1.0)
    return hrf / hrf.sum()


def regressor(onsets: np.ndarray, durations: np.ndarray, frame_times: np.ndarray) -> np.ndarray:
    """Return an HRF-convolved boxcar regressor sampled at ``frame_times`` (nilearn ``compute_regressor``)."""

    n = frame_times.size
    lo, hi = frame_times.min(), frame_times.max()
    n_hr = (n - 1) / (hi - lo) * (hi * (1 + 1.0 / (n - 1)) - lo - MIN_ONSET) * OVERSAMPLING + 1
    hr_times = np.linspace(lo + MIN_ONSET, hi * (1 + 1.0 / (n - 1)), int(np.rint(n_hr)))
    tmax = hr_times.size
    boxcar = np.zeros(tmax)
    t_on = np.minimum(np.searchsorted(hr_times, onsets), tmax - 1)
    t_off = np.minimum(np.searchsorted(hr_times, onsets + durations), tmax - 1)
    t_off = np.where((t_off < tmax - 1) & (t_off == t_on), t_off + 1, t_off)
    np.add.at(boxcar, t_on, 1.0)
    np.add.at(boxcar, t_off, -1.0)
    boxcar = np.cumsum(boxcar)
    convolved = np.convolve(boxcar, spm_hrf())[:tmax]
    return np.interp(frame_times, hr_times, convolved)


def cosine_drift(frame_times: np.ndarray, high_pass: float = HIGH_PASS_HZ) -> np.ndarray:
    """Return the DCT-II drift basis plus a constant (nilearn ``create_cosine_drift``)."""

    n = frame_times.size
    dt = (frame_times[-1] - frame_times[0]) / (n - 1)
    order = min(n - 1, int(np.floor(2 * n * high_pass * dt)))
    drift = np.zeros((n, order + 1))
    for k in range(1, order + 1):
        drift[:, k - 1] = np.sqrt(2.0 / n) * np.cos((np.pi / n) * (np.arange(n) + 0.5) * k)
    drift[:, -1] = 1.0
    return drift


def whiten(x: np.ndarray, rho: float = AR_RHO) -> np.ndarray:
    """Apply the AR(1) prewhitening transform to the rows of ``x``."""

    out = x.copy()
    out[0] = x[0] * math.sqrt(1.0 - rho**2)
    out[1:] = x[1:] - rho * x[:-1]
    return out


class SlotModel:
    """Residualized information of the block slots of one run layout.

    Cell regressors are sums of slot regressors, so the information matrix of
    any block order is ``A' M A`` for its slot-to-cell assignment ``A`` and the
    whitened, nuisance-residualized slot Gram matrix ``M`` (Schur complement of
    the cue regressor, cosine drift, and constant).
    """

    def __init__(self, screens: dict[str, float], high_pass: float = HIGH_PASS_HZ, rho: float = AR_RHO) -> None:
        """Precompute slot regressors, nuisance (cue, drift, constant), and ``M``."""

        onsets, _, run_s = block_onsets(screens)
        self.run_s = run_s
        self.n_scans = math.ceil(run_s / TR - 1e-9)
        frame_times = np.arange(self.n_scans) * TR
        task_s = TRIALS_PER_BLOCK * trial_duration(screens)
        slots = np.stack([regressor(np.array([t + CUE_DURATION]), np.array([task_s]), frame_times) for t in onsets], 1)
        cue = regressor(onsets, np.full(onsets.size, CUE_DURATION), frame_times)[:, None]
        nuisance = whiten(np.hstack([cue, cosine_drift(frame_times, high_pass)]), rho)
        slots = whiten(slots, rho)
        residual = slots - nuisance @ np.linalg.pinv(nuisance) @ slots
        self.gram = residual.T @ slots

    def efficiencies(self, orders: np.ndarray) -> dict[str, np.ndarray]:
        """Return 1 / (c' I^-1 c) per (n, slots) 0/1 order (1 = the task's second cell) for each contrast."""

        onehot = np.eye(2)[np.atleast_2d(orders)]
        info = np.linalg.inv(onehot.transpose(0, 2, 1) @ self.gram @ onehot)
        contrasts = {"difference": np.array([-1.0, 1.0]), "first": np.array([1.0, 0.0]), "second": np.array([0.0, 1.0])}
        return {name: 1.0 / np.einsum("i,nij,j->n", c, info, c) for name, c in contrasts.items()}


def all_orders() -> np.ndarray:
    """Return every 0/1 order of the run's blocks with ``BLOCKS_PER_CELL`` blocks of each cell."""

    n = 2 * BLOCKS_PER_CELL
    rows = [[1 if k in ones else 0 for k in range(n)] for ones in itertools.combinations(range(n), BLOCKS_PER_CELL)]
    return np.array(rows)


def alternating(first: int) -> np.ndarray:
    """Return the strictly alternating order that starts with cell ``first`` (0 or 1)."""

    return np.array([(first + k) % 2 for k in range(2 * BLOCKS_PER_CELL)])


# ---------------------------------------------------------------------------
# Items and cell assignment
# ---------------------------------------------------------------------------


def load_items(path: Path, runs: dict[str, int]) -> pd.DataFrame:
    """Load and validate the item table (one frame per row, one source pair per frame)."""

    items = pd.read_csv(path, sep="\t" if path.suffix == ".tsv" else ",", keep_default_na=False)
    missing = [c for c in ITEM_COLUMNS if c not in items.columns]
    if missing:
        raise ValueError(f"item table lacks columns {missing}")
    if items.frame_id.duplicated().any():
        raise ValueError("duplicate frame_id values")
    if not set(items.distance) <= {"near", "far"}:
        raise ValueError("distance must be near or far")
    words = Counter(items[list(WORD_COLUMNS)].to_numpy().ravel())
    repeated = [w for w, n in words.items() if n > 1]
    if repeated:
        raise ValueError(f"words shown in more than one frame: {repeated[:10]}")
    per_cell = TRIALS_PER_BLOCK * BLOCKS_PER_CELL
    near = items[items.distance == "near"].groupby("relation").size()
    far = items[items.distance == "far"].groupby("relation").size()
    near = near.reindex(far.index.union(near.index), fill_value=0)
    far = far.reindex(near.index, fill_value=0)
    if ((far - near) < 0).any() or ((far - near) % 2).any():
        raise ValueError("each relation needs at least as many far as near frames, with an even surplus")
    if near.sum() != runs["reldist"] * per_cell or (far - near).sum() != 2 * runs["relsem"] * per_cell:
        raise ValueError(
            f"need {runs['reldist'] * per_cell} near and {runs['reldist'] * per_cell + 2 * runs['relsem'] * per_cell}"
            f" far frames for {runs['relsem']} relsem and {runs['reldist']} reldist runs"
        )
    return items


LABELS = (("reldist", "rel_near"), ("reldist", "rel_far"), ("relsem", "rel_far"), ("relsem", "sem_far"))


def assign_cells(
    items: pd.DataFrame, rng: random.Random, match: list[str], relsem_match: list[str], draws: int
) -> pd.DataFrame:
    """Give each frame its task and cell; keep the best-balanced of ``draws`` seeded splits, then swap.

    Near frames are reldist ``rel_near``. Relation ``r``'s far frames take
    ``n_near(r)`` reldist ``rel_far`` slots and equal relsem ``rel_far`` and
    ``sem_far`` halves. The score is the summed squared standardized mean
    difference between the two cells of each task over ``match``, plus the
    relsem difference over ``relsem_match`` (source-distance measures belong
    there: matching them across near and far would undo the manipulation);
    pairwise swaps of far frames within a relation then lower it until no swap
    helps.
    """

    frames = items.reset_index(drop=True)
    values = np.hstack([_standardized(frames, match), _standardized(frames, relsem_match)])
    shared = np.arange(values.shape[1]) < len(match)
    near_count = Counter(frames.relation[frames.distance == "near"])
    groups = [g.index.to_numpy() for _, g in frames[frames.distance == "far"].groupby("relation", sort=True)]
    best, best_score = None, math.inf
    for _ in range(max(1, draws)):
        labels = np.zeros(len(frames), dtype=int)
        for idx in groups:
            order = list(idx)
            rng.shuffle(order)
            k = near_count[frames.at[order[0], "relation"]]
            half = (len(order) - k) // 2
            for j, i in enumerate(order):
                labels[i] = 1 if j < k else (2 if j < k + half else 3)
        score = _imbalance(values, labels, shared)
        if score < best_score:
            best, best_score = labels, score
    best, best_score = _improve(values, best, groups, best_score, shared)
    frames["task"] = [LABELS[k][0] for k in best]
    frames["cell"] = [LABELS[k][1] for k in best]
    frames.attrs["imbalance"] = best_score
    return frames


def _standardized(frames: pd.DataFrame, columns: list[str]) -> np.ndarray:
    """Return ``columns`` as an (n, c) array of z-scores; blank or missing values count as the column mean."""

    if not columns:
        return np.zeros((len(frames), 0))
    values = frames[list(columns)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    mean = np.nanmean(values, 0)
    values = np.where(np.isnan(values), mean, values)
    scale = values.std(0)
    return (values - mean) / np.where(scale > 0, scale, 1.0)


def _imbalance(values: np.ndarray, labels: np.ndarray, shared: np.ndarray) -> float:
    """Squared standardized mean differences: reldist cells (labels 0-1) over ``shared`` columns, relsem (2-3) over all."""

    means = [values[labels == k].mean(0) for k in range(len(LABELS))]
    return float(((means[0] - means[1])[shared] ** 2).sum() + ((means[2] - means[3]) ** 2).sum())


def _improve(values, labels, groups, score: float, shared: np.ndarray, sweeps: int = 50) -> tuple:
    """Swap far frames between cells within relations while it lowers the imbalance (first improvement)."""

    labels = labels.copy()
    sums = np.stack([values[labels == k].sum(0) for k in range(len(LABELS))])
    counts = np.array([(labels == k).sum() for k in range(len(LABELS))], dtype=float)

    def total(s: np.ndarray) -> float:
        """Return the imbalance for per-label column sums ``s``."""

        means = s / counts[:, None]
        return float(((means[0] - means[1])[shared] ** 2).sum() + ((means[2] - means[3]) ** 2).sum())

    for _ in range(sweeps):
        improved = False
        for idx in groups:
            for i, j in itertools.combinations(sorted(idx), 2):
                a, b = labels[i], labels[j]
                if a == b:
                    continue
                trial = sums.copy()
                trial[a] += values[j] - values[i]
                trial[b] += values[i] - values[j]
                value = total(trial)
                if value < score - 1e-12:
                    sums, score, improved = trial, value, True
                    labels[i], labels[j] = b, a
        if not improved:
            break
    return labels, score


def deal_runs(frames: pd.DataFrame, task: str, n_runs: int, rng: random.Random, match: list[str], draws: int) -> dict:
    """Deal one task's frames to runs: equal per-run relation counts for both cells, balanced ``match`` means.

    Each relation contributes ``n_r // n_runs`` frames per run and cell, and its
    remainder goes to the runs with the fewest frames so far (seeded ties), the
    same runs for both cells. Among ``draws`` seeded dealings of the frames
    themselves, the one with the smallest across-run variance of the
    standardized ``match`` means (summed over cells) is kept. Returns
    ``{frame index: run index}``.
    """

    cells = TASKS[task]
    sub = frames[frames.task == task]
    values = dict(zip(sub.index, _standardized(sub, match)))
    counts = Counter(sub.relation[sub.cell == cells[0]])
    totals = [0] * n_runs
    quota = {}
    for relation in sorted(counts, key=lambda r: (-(counts[r] % n_runs), r)):
        n = counts[relation]
        per_run = [n // n_runs] * n_runs
        order = sorted(range(n_runs), key=lambda k: (totals[k], rng.random()))
        for k in order[: n % n_runs]:
            per_run[k] += 1
        quota[relation] = per_run
        totals = [t + q for t, q in zip(totals, per_run)]
    members = {
        (cell, relation): sorted(sub.index[(sub.cell == cell) & (sub.relation == relation)])
        for cell in cells
        for relation in quota
    }
    best, best_score = None, math.inf
    for _ in range(max(1, draws)):
        runs, score = {}, 0.0
        for cell in cells:
            sums = np.zeros((n_runs, len(match)))
            for relation, per_run in quota.items():
                idx = list(members[(cell, relation)])
                rng.shuffle(idx)
                slots = [k for k, q in enumerate(per_run) for _ in range(q)]
                for i, k in zip(idx, slots):
                    runs[i] = k
                    sums[k] += values[i]
            if match:
                score += float((sums / np.array(totals)[:, None]).var(0).sum())
        if score < best_score:
            best, best_score = runs, score
    return best


def partition_blocks(frames: pd.DataFrame, rng: random.Random, attempts: int = 2000) -> list[list]:
    """Split one run-cell's frames into blocks of ``TRIALS_PER_BLOCK`` with distinct relations.

    Seeded greedy fills place each frame (most frequent relation first) in a
    block without its relation and with the fewest frames of its category;
    the fill with the fewest repeated categories is kept, stopping early at
    the lower bound (categories with more frames than blocks must repeat).
    """

    idx = list(frames.index)
    relation = {i: frames.at[i, "relation"] for i in idx}
    category = {i: frames.at[i, "category"] for i in idx}
    n_blocks = len(idx) // TRIALS_PER_BLOCK
    size = Counter(relation.values())
    bound = sum(max(0, k - n_blocks) for k in Counter(category.values()).values())
    best, best_repeats = None, math.inf
    for _ in range(attempts):
        order = sorted(idx, key=lambda i: (-size[relation[i]], rng.random()))
        blocks = [[] for _ in range(n_blocks)]
        for i in order:
            open_ = [
                b
                for b in range(n_blocks)
                if len(blocks[b]) < TRIALS_PER_BLOCK and all(relation[j] != relation[i] for j in blocks[b])
            ]
            if not open_:
                break
            clash = {b: sum(category[j] == category[i] for j in blocks[b]) for b in open_}
            fewest = min(clash.values())
            blocks[rng.choice([b for b in open_ if clash[b] == fewest])].append(i)
        else:
            repeats = sum(TRIALS_PER_BLOCK - len({category[j] for j in block}) for block in blocks)
            if repeats < best_repeats:
                best, best_repeats = blocks, repeats
            if repeats <= bound:
                break
    if best is None:
        raise RuntimeError("could not partition frames into relation-distinct blocks")
    for block in best:
        rng.shuffle(block)
    return best


def position_patterns(n_blocks: int, rng: random.Random, max_run: int, attempts: int = 100000) -> list[tuple]:
    """Return per-block correct-position patterns (two upper, two lower) with runs <= ``max_run``."""

    patterns = sorted(set(itertools.permutations((UPPER, UPPER, LOWER, LOWER))))
    for _ in range(attempts):
        chosen = [rng.choice(patterns) for _ in range(n_blocks)]
        if longest_run([p for block in chosen for p in block]) <= max_run:
            return chosen
    raise RuntimeError("could not satisfy the position-run constraint")


def longest_run(values: list) -> int:
    """Return the length of the longest run of identical consecutive values."""

    return max(len(list(g)) for _, g in itertools.groupby(values)) if values else 0


# ---------------------------------------------------------------------------
# Run tables
# ---------------------------------------------------------------------------


def acquisition_order(runs: dict[str, int]) -> list[tuple[str, int]]:
    """Return (task, run) in scanning order: tasks alternate, relsem first, leftovers at the end."""

    queues = {task: list(range(1, n + 1)) for task, n in runs.items()}
    order = []
    while any(queues.values()):
        for task in TASKS:
            if queues[task]:
                order.append((task, queues[task].pop(0)))
    return order


def build_runs(
    items: pd.DataFrame, seed: int, runs: dict[str, int], args: argparse.Namespace
) -> tuple[list[pd.DataFrame], dict]:
    """Return every run table (acquisition order) and a summary for one subject."""

    rng = random.Random(seed)
    screens = dict(SCREEN_DURATIONS, options=args.response_window)
    model = SlotModel(screens)
    frames = assign_cells(items, rng, args.match_columns, args.relsem_match_columns, args.assignment_draws)
    onsets, fixations, run_s = block_onsets(screens)
    starts = {}
    for task, n in runs.items():
        first = rng.randrange(2)
        starts[task] = [(first + k) % 2 for k in range(n)]
    columns = {"relsem": args.match_columns + args.relsem_match_columns, "reldist": args.match_columns}
    dealt = {task: deal_runs(frames, task, n, rng, columns[task], args.run_draws) for task, n in runs.items()}
    tables, orders = [], {}
    for acquisition, (task, run) in enumerate(acquisition_order(runs), 1):
        order = alternating(starts[task][run - 1])
        orders[f"{task}-{run:02d}"] = order.tolist()
        cells = TASKS[task]
        cell_blocks = {}
        for cell in cells:
            idx = [i for i, k in dealt[task].items() if k == run - 1 and frames.at[i, "cell"] == cell]
            blocks = partition_blocks(frames.loc[sorted(idx)], rng)
            rng.shuffle(blocks)
            cell_blocks[cell] = blocks
        sequence = [cell_blocks[cells[k]].pop() for k in order]
        patterns = position_patterns(len(sequence), rng, MAX_SAME_POSITION_RUN)
        tables.append(_run_table(frames, task, run, acquisition, order, sequence, patterns, onsets, fixations, screens))
    candidates = all_orders()
    every = model.efficiencies(candidates)["difference"]
    chosen = {name: model.efficiencies(np.array(o)) for name, o in orders.items()}
    summary = {
        "run_s": run_s,
        "n_scans_model": model.n_scans,
        "orders": orders,
        "acquisition_order": [f"{task}-{run:02d}" for task, run in acquisition_order(runs)],
        "efficiency": {name: {k: float(v[0]) for k, v in eff.items()} for name, eff in chosen.items()},
        "efficiency_all_orders": {
            "max": float(every.max()),
            "second": float(np.sort(every)[-2]),
            "best_non_alternating": float(
                max(e for e, o in zip(every, candidates) if any(a == b for a, b in itertools.pairwise(o)))
            ),
            "median": float(np.median(every)),
            "min": float(every.min()),
            "n": len(candidates),
        },
        "assignment_imbalance": frames.attrs.get("imbalance"),
    }
    return tables, summary


def _trial_row(frame: pd.Series, cell: str, start: float, correct: int, screens: dict[str, float]) -> dict:
    """Return one trial's design row (words, options, answer, screen onsets)."""

    rule = RULE_OF_CELL[cell]
    answer = frame.d_rel if rule == "rel" else frame.d_sem
    other = frame.d_sem if rule == "rel" else frame.d_rel
    upper, lower = (answer, other) if correct == UPPER else (other, answer)
    row = {
        "event_type": "trial",
        "trial_type": cell,
        "onset": start,
        "duration": trial_duration(screens),
        "cell": cell,
        "rule": rule,
        "distance": DISTANCE_OF_CELL[cell],
        "frame_id": frame.frame_id,
        "relation_name": frame.relation,
        "relation_category": frame.category,
        "word_a": "",
        "word_b": "",
        "word_c": frame.c,
        "d_rel": frame.d_rel,
        "d_sem": frame.d_sem,
        "option_upper": upper,
        "option_lower": lower,
        "correct_option": correct,
        "correct_answer": answer,
    }
    t = start
    for name in SCREENS:
        row[f"onset_{name}"] = t
        t += screens[name]
    row["response_deadline"] = row["onset_options"] + screens["options"]
    return row


def _run_table(frames, task, run, acquisition, order, sequence, patterns, onsets, fixations, screens) -> pd.DataFrame:
    """Lay out fixation, cue, and trial rows with planned onsets for one run."""

    rows = [
        {"event_type": "fixation", "trial_type": "fixation", "onset": t, "duration": d, "rule": "", "distance": ""}
        for t, d in fixations
    ]
    trial_s, trial_idx = trial_duration(screens), 0
    for block_idx, (k, block, pattern, onset) in enumerate(zip(order, sequence, patterns, onsets), 1):
        cell = TASKS[task][k]
        rows.append(
            {
                "event_type": "cue",
                "trial_type": "cue",
                "onset": onset,
                "duration": CUE_DURATION,
                "block_idx": block_idx,
                "cell": cell,
                "rule": RULE_OF_CELL[cell],
                "distance": DISTANCE_OF_CELL[cell],
            }
        )
        for position, (i, correct) in enumerate(zip(block, pattern)):
            trial_idx += 1
            frame = frames.loc[i]
            row = _trial_row(frame, cell, onset + CUE_DURATION + position * trial_s, correct, screens)
            row |= {"block_idx": block_idx, "trial_idx": trial_idx, "trial_in_block": position + 1}
            row |= {"word_a": frame.a, "word_b": frame.b}
            rows.append(row)
    table = pd.DataFrame(rows).sort_values(["onset", "event_type"], kind="stable").reset_index(drop=True)
    table.insert(0, "task", task)
    table.insert(1, "run", run)
    table.insert(2, "acquisition", acquisition)
    return table


# ---------------------------------------------------------------------------
# Practice
# ---------------------------------------------------------------------------


def build_practice(items: pd.DataFrame, seed: int, args: argparse.Namespace) -> pd.DataFrame:
    """Return one practice table: every practice frame once in ``PRACTICE_CELLS`` blocks, feedback on."""

    rng = random.Random(seed)
    missing = [c for c in PRACTICE_COLUMNS if c not in items.columns]
    if missing:
        raise ValueError(f"practice table lacks columns {missing}")
    frames = items.reset_index(drop=True).copy()
    order = list(frames.index)
    rng.shuffle(order)
    cells = PRACTICE_CELLS[: len(order) // TRIALS_PER_BLOCK]
    screens = dict(SCREEN_DURATIONS, options=args.response_window, post=args.practice_feedback)
    patterns = position_patterns(len(cells), rng, MAX_SAME_POSITION_RUN)
    trial_s = trial_duration(screens)
    rows, t, trial_idx = [], 0.0, 0
    for b, cell in enumerate(cells):
        distance = DISTANCE_OF_CELL[cell]
        rows.append(
            {
                "event_type": "cue",
                "trial_type": "cue",
                "onset": t,
                "duration": CUE_DURATION,
                "block_idx": b + 1,
                "cell": cell,
                "rule": RULE_OF_CELL[cell],
                "distance": distance,
            }
        )
        t += CUE_DURATION
        for k, correct in enumerate(patterns[b]):
            frame = frames.loc[order[b * TRIALS_PER_BLOCK + k]]
            trial_idx += 1
            row = _trial_row(frame, cell, t, correct, screens)
            row |= {"block_idx": b + 1, "trial_idx": trial_idx, "trial_in_block": k + 1}
            row |= {"word_a": frame[f"a_{distance}"], "word_b": frame[f"b_{distance}"]}
            rows.append(row)
            t += trial_s
        rows.append(
            {
                "event_type": "fixation",
                "trial_type": "fixation",
                "onset": t,
                "duration": args.practice_rest,
                "rule": "",
                "distance": "",
            }
        )
        t += args.practice_rest
    table = pd.DataFrame(rows)
    table.insert(0, "task", PRACTICE_TASK)
    table.insert(1, "run", 0)
    table.insert(2, "acquisition", 0)
    table["feedback"] = True
    return table


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def run_diagnostics(tables: list[pd.DataFrame], items: pd.DataFrame, runs: dict[str, int], summary: dict) -> dict:
    """Assert the cell, order, timing, position, relation, and no-repetition invariants."""

    per_cell = TRIALS_PER_BLOCK * BLOCKS_PER_CELL
    trials = pd.concat([t[t.event_type == "trial"] for t in tables], ignore_index=True)
    assert len(tables) == sum(runs.values())
    assert [int(t.acquisition.iloc[0]) for t in tables] == list(range(1, len(tables) + 1))
    runner_up = summary["efficiency_all_orders"]["second"]
    for table in tables:
        task, run = table.task.iloc[0], int(table.run.iloc[0])
        cues = table[table.event_type == "cue"]
        run_trials = table[table.event_type == "trial"]
        assert len(cues) == 2 * BLOCKS_PER_CELL and len(run_trials) == 2 * per_cell
        assert set(run_trials.cell) == set(TASKS[task]) and (run_trials.cell.value_counts() == per_cell).all()
        cells = cues.cell.tolist()
        assert all(a != b for a, b in itertools.pairwise(cells)), f"{task} run {run} does not alternate"
        assert (table.event_type == "fixation").sum() == 3
        for _, block in run_trials.groupby("block_idx"):
            assert len(block) == TRIALS_PER_BLOCK and block.cell.nunique() == 1
            assert (block.correct_option == UPPER).sum() == TRIALS_PER_BLOCK // 2
            assert block.relation_name.nunique() == TRIALS_PER_BLOCK
        assert longest_run(run_trials.correct_option.tolist()) <= MAX_SAME_POSITION_RUN
        end = table.onset + table.duration
        assert abs(end.max() - summary["run_s"]) < 1e-6 and abs(table.onset.min()) < 1e-9
        assert np.allclose(table.onset.iloc[1:].to_numpy(), end.iloc[:-1].to_numpy())
        efficiency = summary["efficiency"][f"{task}-{run:02d}"]["difference"]
        assert efficiency >= runner_up - 1e-12, "the alternating order is not among the two most efficient"
        counts = run_trials.groupby(["cell", "relation_name"]).size().unstack(0, fill_value=0)
        assert (counts[TASKS[task][0]] == counts[TASKS[task][1]]).all(), f"{task} run {run} cells differ in relations"
    for task in TASKS:
        firsts = [t[t.event_type == "cue"].cell.iloc[0] for t in tables if t.task.iloc[0] == task]
        assert abs(firsts.count(TASKS[task][0]) - firsts.count(TASKS[task][1])) <= 1
    per_frame = trials.groupby("frame_id").size()
    assert per_frame.index.size == len(items) and (per_frame == 1).all(), "a frame is missing or repeated"
    words = Counter(trials[["word_a", "word_b", "word_c", "d_rel", "d_sem"]].to_numpy().ravel())
    assert max(words.values()) == 1, "a displayed word repeats in the session"
    distance = items.set_index("frame_id").distance
    assert (trials.distance.to_numpy() == distance.loc[trials.frame_id].to_numpy()).all()
    answer = np.where(trials.rule == "rel", trials.d_rel, trials.d_sem)
    assert (trials.correct_answer.to_numpy() == answer).all()
    upper = np.where(trials.correct_option == UPPER, trials.correct_answer, "")
    assert ((upper == "") | (upper == trials.option_upper.to_numpy())).all()
    return {
        "n_trials": len(trials),
        "trials_per_task_cell": {f"{t}/{c}": int(n) for (t, c), n in trials.groupby(["task", "cell"]).size().items()},
        "upper_rate": float((trials.correct_option == UPPER).mean()),
        "longest_position_run": max(longest_run(t[t.event_type == "trial"].correct_option.tolist()) for t in tables),
        "max_word_repetition": max(words.values()),
        "words_shown": len(words),
        "relations": int(trials.relation_name.nunique()),
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _jsonable(value):
    """Convert NumPy scalars and arrays (and tuple keys) for ``json.dumps``."""

    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def sha256(path: Path) -> str:
    """Return the SHA-256 of a file."""

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def design_name(sub_id: str, ses_id: str, task: str, run: int) -> str:
    """Return the design CSV name of one run (``run`` 0 is the practice design)."""

    label = "practice" if run == 0 else f"run-{run:02d}"
    return f"{sub_id}_{ses_id}_task-{task}{TASK_SUFFIX}_{label}_design.csv"


def export(tables: list[pd.DataFrame], out_dir: Path, sub_id: str, ses_id: str, extra: dict, kind: str) -> list[Path]:
    """Write one design CSV per run (provenance in every row) and the session sidecar."""

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for table in tables:
        path = out_dir / design_name(sub_id, ses_id, table.task.iloc[0], int(table.run.iloc[0]))
        table = table.assign(
            seed=extra["seed"], item_table_sha256=extra["item_table_sha256"], generator_sha256=extra["generator_sha256"]
        )
        for column in INTEGER_COLUMNS:
            if column in table:
                table[column] = table[column].astype("Int64")
        table.to_csv(path, index=False, float_format="%.4f")
        paths.append(path)
    sidecar = out_dir / f"{sub_id}_{ses_id}_task-{PRACTICE_TASK}{TASK_SUFFIX}_{kind}.json"
    sidecar.write_text(
        json.dumps(
            {**extra, "files": {p.name: sha256(p) for p in paths}}, indent=2, ensure_ascii=False, default=_jsonable
        )
        + "\n"
    )
    return paths


def main() -> None:
    """Parse arguments, build and check the designs, and write them."""

    parser = argparse.ArgumentParser(description="Generate relsem and reldist localizer design CSVs")
    parser.add_argument("--items", type=Path, help="item table (TSV/CSV, one frame and one source pair per row)")
    parser.add_argument("--practice-items", type=Path, help="practice item table; writes the practice design instead")
    parser.add_argument("--subject", "-p", required=True)
    parser.add_argument("--session", "-s", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--relsem-runs", type=int, default=4)
    parser.add_argument("--reldist-runs", type=int, default=4)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "output")
    parser.add_argument("--response-window", type=float, default=SCREEN_DURATIONS["options"])
    parser.add_argument("--match-columns", nargs="*", default=[], help="balanced between the cells of both tasks")
    parser.add_argument(
        "--relsem-match-columns", nargs="*", default=[], help="balanced in relsem only (source-distance measures)"
    )
    parser.add_argument("--assignment-draws", type=int, default=2000)
    parser.add_argument("--run-draws", type=int, default=500)
    parser.add_argument("--practice-feedback", type=float, default=1.0)
    parser.add_argument("--practice-rest", type=float, default=4.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    np.random.seed(args.seed)
    random.seed(args.seed)
    sub_id, ses_id = f"sub-{int(args.subject):02d}", f"ses-{args.session:02d}"
    out_dir = args.output_dir / "sourcedata" / sub_id / ses_id
    extra = {"subject": sub_id, "session": ses_id, "seed": args.seed, "generator_sha256": sha256(Path(__file__))}
    if args.practice_items is not None:
        items = pd.read_csv(
            args.practice_items, sep="\t" if args.practice_items.suffix == ".tsv" else ",", keep_default_na=False
        )
        extra |= {"item_table": args.practice_items.name, "item_table_sha256": sha256(args.practice_items)}
        export([build_practice(items, args.seed, args)], out_dir, sub_id, ses_id, extra, "practice")
        return
    runs = {"relsem": args.relsem_runs, "reldist": args.reldist_runs}
    items = load_items(args.items, runs)
    tables, summary = build_runs(items, args.seed, runs, args)
    diagnostics = run_diagnostics(tables, items, runs, summary)
    extra |= {
        "tasks": {task: list(cells) for task, cells in TASKS.items()},
        "runs": runs,
        "item_table": args.items.name,
        "item_table_sha256": sha256(args.items),
        "n_volumes": N_VOLUMES,
        "tr": TR,
        "screens": dict(SCREEN_DURATIONS, options=args.response_window),
        "cue_s": CUE_DURATION,
        "fixation_s": {"lead": LEAD_FIXATION, "mid": MID_FIXATION, "end": END_FIXATION},
        "blocks_per_cell": BLOCKS_PER_CELL,
        "trials_per_block": TRIALS_PER_BLOCK,
        **summary,
        "diagnostics": diagnostics,
        "settings": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
    }
    paths = export(tables, out_dir, sub_id, ses_id, extra, "design")
    log.info("wrote %d design files to %s", len(paths), out_dir)
    log.info("diagnostics: %s", json.dumps(extra["diagnostics"], ensure_ascii=False, default=_jsonable))


if __name__ == "__main__":
    main()
