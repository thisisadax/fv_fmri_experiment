#!/usr/bin/env python3
"""Generate session/run CSV files for the 64-relation fMRI analogy experiment.

Adapted from experiment_hakwan/prepare_sessions.py with:
- 64 relations selected via farthest-point sampling (from 80)
- 5 rounds x 16 groups algebraic template (instead of 4 x 20)
- 5 reps/condition/run, 25 blocks/run (instead of 4 reps, 21 blocks)
- Pair reuse across runs (unique within each run)
- 13/12 probe-side balance (25 total probes per condition)
"""

import argparse
import json
import logging
from itertools import combinations
from pathlib import Path
import random

import numpy as np
import pandas as pd
import torch
from tqdm import tqdm

log = logging.getLogger(__name__)

N_CONDITIONS = 64
N_CONDS_PER_RUN = 4
N_REPS_PER_COND_PER_RUN = 5
N_REST_BLOCKS_PER_RUN = 5
N_BLOCKS_PER_RUN = N_CONDS_PER_RUN * N_REPS_PER_COND_PER_RUN + N_REST_BLOCKS_PER_RUN  # 25
N_RUNS_PER_COND = 5
N_ROUNDS = 5
N_GROUPS = 16  # N_CONDITIONS // N_CONDS_PER_RUN
N_RUNS = N_ROUNDS * N_GROUPS  # 80
N_SESSIONS = 8
N_RUNS_PER_SESSION = 10
N_TRIALS_PER_BLOCK = 5  # 4 examples + 1 probe
REST_COND_ID = N_CONDS_PER_RUN  # index 4 used for rest/jingle blocks


def _normalize_relation_key(s):
    """Canonical form for matching relation names to representation keys.

    Representation files may use different separators depending on the
    language (e.g. Korean keys replace spaces/colons while English keys
    only replace slashes).  Normalising both sides to the same form
    lets us do a reliable lookup regardless of convention.
    """
    return s.replace(' ', '_').replace(':', '-').replace('/', '-')


def _load_representations(representations_file, relation_names):
    """Load representation vectors aligned with *relation_names*.

    Returns an (N, D) numpy array in the same order as *relation_names*.
    """
    reps = torch.load(representations_file, weights_only=True, map_location='cpu')
    lookup = {_normalize_relation_key(k): k for k in reps}
    vecs = []
    for name in relation_names:
        key = lookup[_normalize_relation_key(name)]
        vecs.append(reps[key].numpy())
    return np.stack(vecs)


# ---------------------------------------------------------------------------
# Stage 0 — relation selection (farthest-point sampling)
# ---------------------------------------------------------------------------

def select_relations(relation_names, representations_file, n_select):
    """Select n_select relations that are maximally dissimilar via farthest-point sampling.

    Returns the indices (into the original 80-relation list) of the selected relations.
    """
    V = _load_representations(representations_file, relation_names)

    norms = np.linalg.norm(V, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    V_norm = V / norms
    cosine_dist = 1.0 - V_norm @ V_norm.T

    # Greedy farthest-point sampling
    # Seed with the pair having maximum distance
    i, j = np.unravel_index(cosine_dist.argmax(), cosine_dist.shape)
    selected = [i, j]
    min_dist_to_selected = np.minimum(cosine_dist[i], cosine_dist[j])

    while len(selected) < n_select:
        candidates = np.ones(len(relation_names), dtype=bool)
        candidates[selected] = False
        candidate_dists = min_dist_to_selected.copy()
        candidate_dists[~candidates] = -1.0
        next_idx = candidate_dists.argmax()
        selected.append(next_idx)
        min_dist_to_selected = np.minimum(min_dist_to_selected, cosine_dist[next_idx])

    selected.sort()
    log.info(f"Selected {n_select} relations from {len(relation_names)} "
             f"(min pairwise cosine dist among selected: "
             f"{cosine_dist[np.ix_(selected, selected)][np.triu_indices(n_select, k=1)].min():.4f})")
    return selected


# ---------------------------------------------------------------------------
# Stage 1 — run-assignment template
# ---------------------------------------------------------------------------

def construct_template():
    """Algebraic construction: 80 runs x 4 slots.

    5 rounds x 16 groups. Conditions indexed as (x, y) with x in {0..3},
    y in {0..15}, flattened to x*16 + y. In round r, group g the four
    conditions are (x, (g - r*x) mod 16) for x in {0..3}.

    Guarantees:
    - Each of 64 conditions appears exactly 5 times
    - No pair co-occurs in more than 1 run
    - Each condition has exactly 15 co-occurring partners
    """
    template = np.zeros((N_RUNS, N_CONDS_PER_RUN), dtype=int)
    run_to_round = np.zeros(N_RUNS, dtype=int)
    idx = 0
    for r in range(N_ROUNDS):
        for g in range(N_GROUPS):
            template[idx] = [x * N_GROUPS + (g - r * x) % N_GROUPS for x in range(N_CONDS_PER_RUN)]
            run_to_round[idx] = r
            idx += 1
    return template, run_to_round


# ---------------------------------------------------------------------------
# Stage 2 — permutation optimization
# ---------------------------------------------------------------------------

def optimize_permutation(template, relation_names, similarity_file, n_iterations):
    """Maximize within-run representational dissimilarity via hill-climbing."""
    perm = np.random.permutation(N_CONDITIONS)
    if similarity_file is None:
        return perm, None

    V = _load_representations(similarity_file, relation_names)
    norms = np.linalg.norm(V, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    V_norm = V / norms
    D = 1 - V_norm @ V_norm.T

    pi, pj = np.triu_indices(N_CONDS_PER_RUN, k=1)
    rels = perm[template]
    best = D[rels[:, pi], rels[:, pj]].mean()
    initial = best

    for _ in tqdm(range(n_iterations), desc="Optimizing permutation"):
        a, b = np.random.choice(N_CONDITIONS, 2, replace=False)
        perm[a], perm[b] = perm[b], perm[a]
        rels = perm[template]
        s = D[rels[:, pi], rels[:, pj]].mean()
        if s > best:
            best = s
        else:
            perm[a], perm[b] = perm[b], perm[a]

    log.info(f"Mean within-run dissimilarity: {initial:.4f} -> {best:.4f} (+{best - initial:.4f})")
    return perm, D


# ---------------------------------------------------------------------------
# Stage 3 — session assignment
# ---------------------------------------------------------------------------

def assign_sessions(template, perm, run_to_round, max_restarts=500):
    """Assign 80 runs to 8 sessions of 10, no relation repeated within a session.

    Uses backtracking with most-constrained-variable ordering: at each step,
    picks the unassigned run with the fewest valid session options, pruning
    the search tree aggressively.
    """
    for attempt in range(max_restarts):
        run_to_session = np.full(N_RUNS, -1, dtype=int)
        counts = np.zeros(N_SESSIONS, dtype=int)
        seen = np.zeros((N_SESSIONS, N_CONDITIONS), dtype=bool)

        if _assign_all_backtrack(template, perm, run_to_session, counts, seen):
            log.info(f"Session assignment found after {attempt + 1} restarts")
            return run_to_session

    raise RuntimeError("Failed to assign sessions after max restarts")


def _valid_sessions(run, template, perm, run_to_session, counts, seen):
    """Return list of sessions that run can be assigned to."""
    rels = perm[template[run]]
    return [s for s in range(N_SESSIONS)
            if counts[s] < N_RUNS_PER_SESSION and not seen[s, rels].any()]


def _assign_all_backtrack(template, perm, run_to_session, counts, seen):
    """Backtracking search with most-constrained-variable (MRV) ordering."""
    unassigned = [r for r in range(N_RUNS) if run_to_session[r] == -1]
    if not unassigned:
        return True

    # MRV: pick the run with fewest valid session options
    best_run = None
    best_opts = None
    best_n = N_SESSIONS + 1
    for run in unassigned:
        opts = _valid_sessions(run, template, perm, run_to_session, counts, seen)
        if len(opts) == 0:
            return False  # dead end
        if len(opts) < best_n:
            best_n = len(opts)
            best_run = run
            best_opts = opts
            if best_n == 1:
                break  # can't do better

    random.shuffle(best_opts)
    # Prefer least-filled sessions (stable sort preserves shuffle for ties)
    best_opts.sort(key=lambda s: counts[s])

    rels = perm[template[best_run]]
    for s in best_opts:
        run_to_session[best_run] = s
        counts[s] += 1
        seen[s, rels] = True

        if _assign_all_backtrack(template, perm, run_to_session, counts, seen):
            return True

        run_to_session[best_run] = -1
        counts[s] -= 1
        seen[s, rels] = False

    return False


# ---------------------------------------------------------------------------
# Stage 4 — block ordering
# ---------------------------------------------------------------------------

def score_order(seq):
    """Score a block ordering: (n_consec_penalty, min_gap, min_baseline_edge_dist, n_unique_transitions).

    Consecutive-repeat penalty is negative count (0 is best).  This ensures
    an ordering with fewer consecutive repeats always beats one with more,
    while still ranking among orders with the same repeat count.
    """
    n_consec = int(np.sum(seq[:-1] == seq[1:]))
    min_gap = min(
        np.diff(np.where(seq == c)[0]).min() if (seq == c).sum() > 1 else len(seq)
        for c in np.unique(seq)
    )
    baseline_pos = np.where(seq == REST_COND_ID)[0]
    edge_dist = min(baseline_pos.min(), len(seq) - 1 - baseline_pos.max())
    return -n_consec, min_gap, edge_dist, len(set(zip(seq[:-1], seq[1:])))


def order_blocks(n_iterations):
    """Monte-Carlo sample best block ordering for each of 80 runs."""
    pool = np.array(
        [0] * N_REPS_PER_COND_PER_RUN
        + [1] * N_REPS_PER_COND_PER_RUN
        + [2] * N_REPS_PER_COND_PER_RUN
        + [3] * N_REPS_PER_COND_PER_RUN
        + [REST_COND_ID] * N_REST_BLOCKS_PER_RUN
    )
    orders = np.zeros((N_RUNS, N_BLOCKS_PER_RUN), dtype=int)
    for r in tqdm(range(N_RUNS), desc="Ordering blocks"):
        best_seq, best_score = None, (-len(pool), 0, 0, 0)
        for _ in range(n_iterations):
            np.random.shuffle(pool)
            s = score_order(pool)
            if s > best_score:
                best_score = s
                best_seq = pool.copy()
        orders[r] = best_seq
    return orders


# ---------------------------------------------------------------------------
# Stage 5 — trial selection
# ---------------------------------------------------------------------------

def _select_pairs(pairs, indices, n_needed):
    """Shuffle *indices* and greedily pick *n_needed* with no first-word collisions.

    Returns the selected index list, or None if too few qualify.
    """
    random.shuffle(indices)
    selected, seen_w1 = [], set()
    for i in indices:
        w1 = pairs[i].split(':')[0]
        if w1 not in seen_w1:
            seen_w1.add(w1)
            selected.append(i)
            if len(selected) == n_needed:
                return selected
    return None


def _check_co_occurrences(chunks, seen_co, pairs):
    """Verify no word-pair combination in *chunks* repeats one in *seen_co*.

    Uses (word1, word2) identity so duplicates in the pair list are handled.
    Returns the set of new co-occurrences if valid, or None on collision.
    """
    new_cos = set()
    for chunk in chunks:
        word_pairs = [tuple(pairs[i].split(':')) for i in chunk]
        for wp_a, wp_b in combinations(word_pairs, 2):
            key = tuple(sorted([wp_a, wp_b]))
            if key in seen_co or key in new_cos:
                return None
            new_cos.add(key)
    return new_cos


def _build_block(pairs, dists, chunk, correct_option):
    """Build the trial list (4 examples + 1 probe) for one block chunk."""
    probe_i, example_is = chunk[0], chunk[1:]
    block = []
    for i in example_is:
        w1, w2 = pairs[i].split(':')
        block.append({'word1': w1, 'word2': w2, 'type': 'example'})
    w1, w2 = pairs[probe_i].split(':')
    distractor = random.choice(dists[probe_i]).lower()
    if correct_option == 1:
        opt1, opt2 = w2.lower(), distractor
    else:
        opt1, opt2 = distractor, w2.lower()
    block.append({
        'word1': w1, 'word2': w2,
        'option_1': opt1, 'option_2': opt2,
        'correct_option': correct_option,
        'type': 'probe',
    })
    return block


def select_trials(relation_data, perm, template, max_retries=10000):
    """Select 25 pairs per relation per run (5 blocks x 5).

    Pairs may be reused across different runs but are unique within each run.
    No first-word collisions within a run.
    No pair co-occurrence repeats across blocks of the same relation.
    Probes get one randomly sampled distractor; correct-option position uses
    a 13/12 balance across the 25 total probes per condition.
    """
    rel_runs = {i: [] for i in range(N_CONDITIONS)}
    for r in range(N_RUNS):
        for cond, rel in enumerate(perm[template[r]]):
            rel_runs[rel].append((r, cond))

    # Probe balance: runs 0-2 → 3 left / 2 right, runs 3-4 → 2 left / 3 right
    # Total per relation: 13 option_1 / 12 option_2
    balance_pattern = [(3, 2), (3, 2), (3, 2), (2, 3), (2, 3)]
    n_needed = N_TRIALS_PER_BLOCK * N_REPS_PER_COND_PER_RUN

    trials = {}
    for rel in range(N_CONDITIONS):
        pairs = relation_data[rel]['relation_pairs']
        dists = relation_data[rel]['distractors']
        n_usable = min(len(pairs), len(dists))
        indices = list(range(n_usable))
        seen_co = set()

        for run_num, (r_idx, cond) in enumerate(rel_runs[rel]):
            n_left, _ = balance_pattern[run_num]
            for _ in range(max_retries):
                selected = _select_pairs(pairs, indices, n_needed)
                if selected is None: continue
                chunks = [selected[b * N_TRIALS_PER_BLOCK:(b + 1) * N_TRIALS_PER_BLOCK] for b in range(N_REPS_PER_COND_PER_RUN)]
                new_cos = _check_co_occurrences(chunks, seen_co, pairs)
                if new_cos is None: continue
                seen_co |= new_cos
                sides = [1] * n_left + [2] * (N_REPS_PER_COND_PER_RUN - n_left)
                random.shuffle(sides)
                for blk, chunk in enumerate(chunks):
                    trials[(r_idx, cond, blk)] = _build_block(pairs, dists, chunk, sides[blk])
                break
            else:
                raise RuntimeError(
                    f"Failed to assign pairs for relation {rel}, run {run_num}")

    return trials


# ---------------------------------------------------------------------------
# Stage 6 — CSV export
# ---------------------------------------------------------------------------

BASELINE_ROW = dict(
    relation_idx=-1, word1='baseline', word2='baseline',
    option_1='', option_2='',
    relation_name='baseline', relation_category='baseline',
    trial_type='baseline', correct_response='',
)


def export_subject(output_dir, language, subj, template, perm,
                   run_to_session, orders, run_trials, relation_data):
    """Write per-run CSVs for a single subject with shuffled session/run order."""
    session_order = list(range(N_SESSIONS))
    random.shuffle(session_order)

    sub_id = f"sub-{subj:02d}"
    task = f"analogy{language.capitalize()}"

    for new_sess, old_sess in enumerate(session_order):
        ses_id = f"ses-{new_sess + 1:02d}"
        sess_runs = np.where(run_to_session == old_sess)[0].tolist()
        random.shuffle(sess_runs)

        for local, r in enumerate(sess_runs, 1):
            prefix = f"{sub_id}_{ses_id}_task-{task}_run-{local:02d}"
            path = output_dir / "sourcedata" / sub_id / ses_id / f"{prefix}_design.csv"
            path.parent.mkdir(parents=True, exist_ok=True)

            rows = []
            cond_blk = [0] * N_CONDS_PER_RUN
            for seq, cond in enumerate(orders[r], 1):
                if cond == REST_COND_ID:
                    rows.append({**BASELINE_ROW, 'trial_idx': seq})
                else:
                    rel = perm[template[r][cond]]
                    b = cond_blk[cond]
                    cond_blk[cond] += 1
                    meta = relation_data[rel]
                    for t in run_trials[(r, cond, b)]:
                        rows.append({
                            'trial_idx': seq, 'relation_idx': rel,
                            'word1': t['word1'], 'word2': t['word2'],
                            'option_1': t.get('option_1', ''),
                            'option_2': t.get('option_2', ''),
                            'relation_name': meta['relation_name'],
                            'relation_category': meta['relation_category'],
                            'trial_type': t['type'],
                            'correct_response': t.get('correct_option', ''),
                        })
            pd.DataFrame(rows).to_csv(path, index=False)


# ---------------------------------------------------------------------------
# Stage 7 — diagnostics
# ---------------------------------------------------------------------------

def run_diagnostics(template, perm, run_to_session, orders, run_trials, D=None):
    """Verify key invariants."""
    print("\n" + "=" * 50)
    print("DIAGNOSTICS")
    print("=" * 50)

    # Each relation co-occurs with exactly 15 unique others
    co = {i: set() for i in range(N_CONDITIONS)}
    for r in range(N_RUNS):
        rels = set(perm[template[r]].tolist())
        for rel in rels:
            co[rel] |= rels - {rel}
    counts = [len(co[i]) for i in range(N_CONDITIONS)]
    assert min(counts) == max(counts) == 15
    print("1. Co-occurrences per relation: all exactly 15")

    # No session has duplicate relations
    for s in range(N_SESSIONS):
        rels = [rel for r in np.where(run_to_session == s)[0]
                for rel in perm[template[r]]]
        assert len(rels) == len(set(rels))
    print("2. No session relation duplicates")

    # Probe balance + first-word collision check
    left = np.zeros(N_CONDITIONS, dtype=int)
    right = np.zeros(N_CONDITIONS, dtype=int)
    collisions = 0
    for r in range(N_RUNS):
        for cond, rel in enumerate(perm[template[r]]):
            w1s = set()
            for b in range(N_REPS_PER_COND_PER_RUN):
                for t in run_trials[(r, cond, b)]:
                    a = t['word1']
                    if a in w1s:
                        collisions += 1
                    w1s.add(a)
                    if t['type'] == 'probe':
                        if t['correct_option'] == 1:
                            left[rel] += 1
                        else:
                            right[rel] += 1
    assert left.min() == left.max() == 13
    assert right.min() == right.max() == 12
    assert collisions == 0
    print("3. Probe balance: all 13 option_1 / 12 option_2 per relation")
    print("4. No first-word collisions within runs")

    # No pair co-occurrence repeats across blocks of the same relation
    rel_runs = {i: [] for i in range(N_CONDITIONS)}
    for r in range(N_RUNS):
        for cond, rel in enumerate(perm[template[r]]):
            rel_runs[rel].append((r, cond))
    for rel in range(N_CONDITIONS):
        seen = set()
        for r_idx, cond in rel_runs[rel]:
            for b in range(N_REPS_PER_COND_PER_RUN):
                pairs = [(t['word1'], t['word2']) for t in run_trials[(r_idx, cond, b)]]
                for a, b_ in combinations(pairs, 2):
                    key = tuple(sorted([a, b_]))
                    assert key not in seen, f"Pair co-occurrence repeat: {key} in relation {rel}"
                    seen.add(key)
    print("5. No pair co-occurrence repeats across blocks")

    if D is not None:
        pi, pj = np.triu_indices(N_CONDS_PER_RUN, k=1)
        d = [D[perm[template[r]][pi], perm[template[r]][pj]].mean()
             for r in range(N_RUNS)]
        print(f"6. Within-run dissimilarity: {np.mean(d):.4f} +/- {np.std(d):.4f}")

    print("=" * 50 + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate session CSVs for the 64-relation fMRI experiment")
    parser.add_argument("--language", required=True)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--relation-representations", type=Path, default=None,
                        help="Path to representations .pt file (used for both "
                             "relation selection and permutation optimization)")
    parser.add_argument("--n-select", type=int, default=N_CONDITIONS,
                        help=f"Number of relations to select (default: {N_CONDITIONS})")
    parser.add_argument("--n-subjects", type=int, default=8)
    parser.add_argument("--n-iter-similarity", type=int, default=1_000_000)
    parser.add_argument("--n-iter-ordering", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    np.random.seed(args.seed)
    random.seed(args.seed)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    lang_dir = args.data_root / args.language
    relation_files = sorted(lang_dir.rglob("*.json"))
    n_total = len(relation_files)
    assert n_total >= args.n_select, (
        f"Need at least {args.n_select} relation JSONs, found {n_total}")

    all_relation_data = []
    for f in relation_files:
        with open(f) as fh:
            d = json.load(fh)
        all_relation_data.append(d)

    all_relation_names = [d['relation_name'] for d in all_relation_data]

    # Stage 0: select the most dissimilar relations
    if args.relation_representations is not None and args.n_select < n_total:
        log.info(f"Stage 0: Selecting {args.n_select} relations from {n_total}...")
        selected_indices = select_relations(
            all_relation_names, args.relation_representations, args.n_select)
    else:
        if args.n_select < n_total:
            log.warning("No representations file provided; selecting first %d relations", args.n_select)
        selected_indices = list(range(args.n_select))

    relation_data = [all_relation_data[i] for i in selected_indices]
    relation_names = [all_relation_names[i] for i in selected_indices]
    assert len(relation_data) == N_CONDITIONS

    # Save the selection mapping for reproducibility
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    selection_info = {
        'n_total': n_total,
        'n_selected': args.n_select,
        'selected_indices': [int(i) for i in selected_indices],
        'selected_names': relation_names,
        'excluded_names': [n for i, n in enumerate(all_relation_names) if i not in selected_indices],
    }
    with open(output_dir / 'relation_selection.json', 'w') as f:
        json.dump(selection_info, f, indent=2)
    log.info(f"Saved relation selection to {output_dir / 'relation_selection.json'}")

    log.info("Stage 1: Constructing template...")
    template, run_to_round = construct_template()

    log.info("Stage 2: Optimizing permutation...")
    perm, D = optimize_permutation(
        template, relation_names, args.relation_representations, args.n_iter_similarity)

    log.info("Stage 3: Assigning sessions...")
    run_to_session = assign_sessions(template, perm, run_to_round)

    for subj in tqdm(range(1, args.n_subjects + 1), desc="Generating subjects"):
        log.info(f"Subject {subj}: ordering, selecting, exporting...")
        orders = order_blocks(args.n_iter_ordering)
        run_trials = select_trials(relation_data, perm, template)
        export_subject(output_dir, args.language, subj, template, perm,
                       run_to_session, orders, run_trials, relation_data)
        run_diagnostics(template, perm, run_to_session, orders, run_trials, D)

    log.info("Done!")


if __name__ == "__main__":
    main()
