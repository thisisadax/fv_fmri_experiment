#!/usr/bin/env python
"""Run one relational localizer run (task relsem or reldist), or the practice block.

Differences from ``run_experiment.py``:

- every screen is flipped at its planned onset (from the first trigger) read
  from the seeded design CSV, so save I/O and frame timing never accumulate
  drift; flips are requested ``cfg.LOC_FLIP_LEAD`` early and their actual
  times are logged with the planned ones;
- nothing is randomized at run time (positions and orders are in the CSV);
- the response window ends at the planned deadline (``run_experiment_4s_deadline``
  style timeout) while the display stays on screen for the whole window;
- events (one 6 s row per trial plus cue rows) are rewritten after every
  trial and cue, with dropped-frame counts and provenance in every row;
- before each run a short screen names the run type (both rules alternating
  in ``relsem``; only the relational rule in ``reldist``); the full
  instructions open the practice and the session's first run.

Reused from the main task: window settings, ``Scanner`` (trigger, TR logging,
``--mode Test``), ``EventLogger`` (clock), and the colon-aligned text and 2AFC
layout (``AnalogyExperiment._init_stimuli`` / ``_get_word_pos``).

Usage (acquisition order is in the design sidecar: relsem 1, reldist 1, relsem 2, ...):
    python run_localizer.py -p 01 -s 10 -t relsem -r 1           # scanner, waits for 's'
    python run_localizer.py -p 01 -s 10 -t reldist -r 1 --mode Test
    python run_localizer.py -p 01 -s 10 --practice               # out-of-scanner practice with feedback
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import psychopy
from psychopy import core, event, logging, visual

sys.path.insert(0, str(Path(__file__).parent))
import config as cfg
from run_experiment import AnalogyExperiment
from utils import EventLogger, Scanner

SCREENS = ("fixation", "word_a", "pair", "word_c", "options", "post")


def sha256(path: Path) -> str:
    """Return the SHA-256 of a file."""

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def repository_commit() -> str:
    """Return the experiment repository's HEAD commit, or ``unknown``."""

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, capture_output=True, text=True, check=True
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=Path(__file__).parent, capture_output=True, text=True, check=True
        )
        return result.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


class LocalizerExperiment(AnalogyExperiment):
    """One relloc run (or practice block) on an absolute schedule from the first trigger."""

    def __init__(self, subject, session, task, run, language, mode, practice=False, screen=1):
        """Load and check the design, open the window, and prepare stimuli and outputs."""

        self.p_info = {"subject": subject, "session": session, "task": task, "run": run, "language": language}
        self.mode, self.practice = mode, practice
        self.stim, self.rows, self.flips = {}, [], {}
        self.task = f"{cfg.LOC_PRACTICE_TASK if practice else task}{language.capitalize()}"
        self.sub_id, self.ses_id = f"sub-{int(subject):02d}", f"ses-{int(session):02d}"
        label = "practice" if practice else f"run-{int(run):02d}"
        base = Path(__file__).parent / cfg.OUTPUT_DIR
        self.design_path = (
            base
            / cfg.SOURCEDATA_DIR
            / self.sub_id
            / self.ses_id
            / (f"{self.sub_id}_{self.ses_id}_task-{self.task}_{label}_design.csv")
        )
        # Only blank cells are missing; words such as "NA" must stay text.
        self.design = pd.read_csv(self.design_path, keep_default_na=False, na_values=[""])
        self._check_design()
        self.acquisition = int(self.design.acquisition.iloc[0])
        self.out_dir = base / self.sub_id / self.ses_id / ("beh" if practice else "func")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.run_ts = datetime.now().astimezone().strftime("%y%m%d%H%M%S")
        self.stem = f"{self.sub_id}_{self.ses_id}_task-{self.task}_{label}"
        logging.LogFile(str(self.out_dir / f"{self.stem}_{self.run_ts}.log"), level=logging.DATA, filemode="w")
        self.win = visual.Window(
            size=cfg.WINDOW_SIZE,
            fullscr=cfg.FULLSCREEN,
            screen=screen,
            monitor=cfg.MONITOR_NAME,
            units=cfg.UNITS,
            color=cfg.BACKGROUND_COLOR,
            waitBlanking=True,
            allowGUI=False,
        )
        self.win.recordFrameIntervals = True
        self.frame_rate = self.win.getActualFrameRate()
        font = cfg.FONT_NAME_KOREAN if language == "korean" else cfg.FONT_NAME
        self.scanner = Scanner(
            self.win, mode=mode, tr=cfg.SCANNER_SETTINGS["TR"], sync_key=cfg.SCANNER_SETTINGS["sync"], font=font
        )
        self.logger = EventLogger()
        self._init_stimuli()
        text = {"win": self.win, "font": font, "alignText": "center"}
        self.stim["cue"] = visual.TextStim(text="", height=cfg.LOC_CUE_HEIGHT, color=cfg.TEXT_COLOR, **text)
        self.stim["rule_label"] = visual.TextStim(
            text="",
            height=cfg.LOC_RULE_LABEL_HEIGHT,
            pos=(0, cfg.LOC_RULE_LABEL_Y),
            color=cfg.LOC_RULE_LABEL_COLOR,
            **text,
        )
        self.stim["feedback"] = visual.TextStim(text="", height=cfg.WORD_HEIGHT, color=cfg.TEXT_COLOR, **text)
        self.provenance = {
            "design": self.design_path.name,
            "design_sha256": sha256(self.design_path),
            "seed": int(self.design.seed.iloc[0]),
            "item_table_sha256": str(self.design.item_table_sha256.iloc[0]),
            "generator_sha256": str(self.design.generator_sha256.iloc[0]),
            "experiment_commit": repository_commit(),
            "psychopy": psychopy.__version__,
            "mode": mode,
            "practice": practice,
            "task": self.task,
            "acquisition": self.acquisition,
            "frame_rate": self.frame_rate,
        }

    # ------------------------------------------------------------------
    # Checks and drawing
    # ------------------------------------------------------------------

    def _check_design(self):
        """Fail before the trigger if the CSV task or timing disagrees with ``config.py``."""

        expected = cfg.LOC_PRACTICE_TASK if self.practice else self.p_info["task"]
        if set(self.design.task) != {expected}:
            raise ValueError(f"design task {set(self.design.task)} is not {expected}")
        trials = self.design[self.design.event_type == "trial"]
        for current, following in itertools.pairwise(SCREENS[:-1]):
            gaps = (trials[f"onset_{following}"] - trials[f"onset_{current}"]).round(4).unique()
            if len(gaps) != 1 or abs(gaps[0] - cfg.LOC_TRIAL_SCREENS[current]) > 1e-3:
                raise ValueError(f"{current} duration in the design differs from LOC_TRIAL_SCREENS: {gaps}")
        window = (trials.response_deadline - trials.onset_options).round(4).unique()
        if len(window) != 1 or abs(window[0] - cfg.LOC_TRIAL_SCREENS["options"]) > 1e-3:
            raise ValueError(f"response window in the design differs from LOC_TRIAL_SCREENS: {window}")
        ends = (self.design.onset + self.design.duration).to_numpy()
        if (abs(self.design.onset.to_numpy()[1:] - ends[:-1]) > 1e-3).any():
            raise ValueError("design events are not contiguous")

    def _rule_text(self, rule):
        """Return the cue word for ``rule`` in the session language."""

        return cfg.LOC_RULE_CUES[self.p_info["language"]][rule]

    def _draw_rule_label(self, rule):
        """Draw the current rule word above the trial display."""

        self.stim["rule_label"].text = self._rule_text(rule)
        self.stim["rule_label"].draw()

    def _draw_words(self, left, right=None):
        """Draw ``left :`` or ``left : right`` with the main task's colon alignment (no flip)."""

        self.stim["word_L"].text = left
        self.stim["word_L"].pos = (self._get_word_pos(left, "left"), 0)
        self.stim["word_L"].draw()
        self.stim["colon"].draw()
        if right:
            self.stim["word_R"].text = right
            self.stim["word_R"].pos = (self._get_word_pos(right, "right"), 0)
            self.stim["word_R"].draw()

    def _draw_options(self, upper, lower):
        """Draw the stacked options with the main task's 2AFC layout (no flip)."""

        for key, word, y in (("opt_up", upper, cfg.AFC_OPTION_Y), ("opt_lo", lower, -cfg.AFC_OPTION_Y)):
            self.stim[key].text = word
            self.stim[key].pos = (self._get_word_pos(word, "option", self.word_offset_x), y)
            self.stim[key].draw()

    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------

    def _wait_until(self, t):
        """Wait on the logger clock until ``t`` while logging TR pulses and honoring Escape."""

        while self.logger.clock.getTime() < t:
            self.scanner.check_for_tr()
            if event.getKeys(keyList=cfg.QUIT_KEYS):
                raise KeyboardInterrupt
            core.wait(0.0005, hogCPUperiod=0.0005)

    def _stamp(self, key):
        """Record the logger-clock time of the flip that shows screen ``key``."""

        self.flips[key] = self.logger.clock.getTime()

    def _flip_at(self, planned, key):
        """Flip the composed screen at its planned onset and return the actual flip time."""

        self._wait_until(planned - cfg.LOC_FLIP_LEAD)
        self.win.callOnFlip(self._stamp, key)
        self.win.flip()
        logging.data(f"flip {key} planned={planned:.4f} actual={self.flips[key]:.4f}")
        return self.flips[key]

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _rest(self, ev):
        """Show fixation for a rest block."""

        self.stim["fixation"].draw()
        self._flip_at(ev["onset"], ("rest", ev["onset"]))

    def _cue(self, ev):
        """Show the 2 s rule cue and log it."""

        self.stim["cue"].text = self._rule_text(ev["rule"])
        self.stim["cue"].draw()
        actual = self._flip_at(ev["onset"], ("cue", ev["block_idx"]))
        self.rows.append(
            {
                "onset": actual,
                "duration": ev["duration"],
                "trial_type": "cue",
                "block_idx": ev["block_idx"],
                "rule": ev["rule"],
                "distance": ev["distance"],
                "planned_onset": ev["onset"],
            }
        )
        self._save_events()

    def _collect(self, ev, options_onset):
        """Poll response keys until the planned deadline; return the first press, if any."""

        first, extra = None, 0
        deadline = ev["response_deadline"] - cfg.LOC_FLIP_LEAD
        while self.logger.clock.getTime() < deadline:
            self.scanner.check_for_tr()
            for key, t in event.getKeys(keyList=cfg.RESPONSE_KEYS + cfg.QUIT_KEYS, timeStamped=self.logger.clock):
                if key in cfg.QUIT_KEYS:
                    raise KeyboardInterrupt
                if first is None:
                    first = (key, t - options_onset)
                else:
                    extra += 1
            core.wait(0.0005, hogCPUperiod=0.0005)
        return first, extra

    def _trial(self, ev):
        """Show one trial at its planned screen onsets, then log and save it."""

        idx, rule = ev["trial_idx"], ev["rule"]
        dropped_before = self.win.nDroppedFrames
        actual = {}
        self.stim["fixation"].draw()
        self._draw_rule_label(rule)
        actual["fixation"] = self._flip_at(ev["onset_fixation"], ("fixation", idx))
        self._draw_words(ev["word_a"])
        self._draw_rule_label(rule)
        actual["word_a"] = self._flip_at(ev["onset_word_a"], ("word_a", idx))
        self._draw_words(ev["word_a"], ev["word_b"])
        self._draw_rule_label(rule)
        actual["pair"] = self._flip_at(ev["onset_pair"], ("pair", idx))
        self._draw_words(ev["word_c"])
        self._draw_rule_label(rule)
        actual["word_c"] = self._flip_at(ev["onset_word_c"], ("word_c", idx))
        self._draw_words(ev["word_c"])
        self._draw_options(ev["option_upper"], ev["option_lower"])
        self._draw_rule_label(rule)
        early = len(event.getKeys(keyList=cfg.RESPONSE_KEYS))
        actual["options"] = self._flip_at(ev["onset_options"], ("options", idx))
        response, extra = self._collect(ev, actual["options"])
        correct_key = cfg.BUTTON_UPPER if int(ev["correct_option"]) == 1 else cfg.BUTTON_LOWER
        key, rt = response if response else (None, None)
        correct = key == correct_key
        outcome = "timeout" if key is None else ("correct" if correct else "incorrect")
        if self.practice:
            self.stim["feedback"].text = cfg.LOC_FEEDBACK_TEXT[self.p_info["language"]][outcome]
            self.stim["feedback"].color = cfg.LOC_FEEDBACK_COLORS[outcome]
            self.stim["feedback"].draw()
        else:
            self.stim["fixation"].draw()
        self._draw_rule_label(rule)
        actual["post"] = self._flip_at(ev["onset_post"], ("post", idx))
        chosen = None if key is None else (ev["option_upper"] if key == cfg.BUTTON_UPPER else ev["option_lower"])
        row = {
            "onset": actual["fixation"],
            "duration": ev["duration"],
            "trial_type": ev["cell"],
            "block_idx": ev["block_idx"],
            "trial_idx": idx,
            "trial_in_block": ev["trial_in_block"],
            "rule": rule,
            "distance": ev["distance"],
            "frame_id": ev["frame_id"],
            "relation_name": ev["relation_name"],
            "relation_category": ev["relation_category"],
            "word_a": ev["word_a"],
            "word_b": ev["word_b"],
            "word_c": ev["word_c"],
            "d_rel": ev["d_rel"],
            "d_sem": ev["d_sem"],
            "option_upper": ev["option_upper"],
            "option_lower": ev["option_lower"],
            "correct_option": ev["correct_option"],
            "correct_answer": ev["correct_answer"],
            "response_key": key,
            "response_time": rt,
            "response_correct": correct,
            "response_timeout": key is None,
            "response_chosen": chosen,
            "n_early_presses": early,
            "n_extra_presses": extra,
            "planned_onset": ev["onset"],
            "onset_options": actual["options"],
            "planned_onset_options": ev["onset_options"],
            "max_flip_lag": max(actual[s] - ev[f"onset_{s}"] for s in SCREENS),
            "n_dropped_frames": self.win.nDroppedFrames - dropped_before,
        }
        self.rows.append(row)
        self._save_events()

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _save_events(self):
        """Rewrite the events TSV (with provenance columns) after every trial and cue."""

        if not self.rows:
            return
        frame = pd.DataFrame(self.rows)
        for name in ("seed", "item_table_sha256", "design_sha256", "experiment_commit"):
            frame[name] = self.provenance[name]
        frame.to_csv(self.out_dir / f"{self.stem}_events_{self.run_ts}.tsv", sep="\t", index=False, na_rep="n/a")

    def _write_sidecar(self, **status):
        """Write the events sidecar JSON with timing and provenance."""

        sidecar = {
            "onset": {"Units": "s", "Description": "actual flip time from the first scanner trigger"},
            "duration": {"Units": "s", "Description": "planned duration"},
            "trial_type": {"Description": "cell (relsem: rel_far, sem_far; reldist: rel_near, rel_far) or cue"},
            "response_time": {"Units": "s", "Description": "from the options flip"},
            "n_volumes_requested": cfg.LOC_N_VOLUMES,
            "planned_run_s": float((self.design.onset + self.design.duration).max()),
            **self.provenance,
            **status,
        }
        path = self.out_dir / f"{self.stem}_events_{self.run_ts}.json"
        path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False, default=str) + "\n")

    def show_instructions(self, text=None):
        """Show instructions paragraph by paragraph, advancing on a button press."""

        text = cfg.LOC_INSTRUCTIONS[self.p_info["language"]] if text is None else text
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        shown = ""
        for paragraph in paragraphs:
            shown = f"{shown}\n\n{paragraph}".strip()
            self.stim["instr"].text = shown
            self.stim["instr"].draw()
            self.stim["hint"].draw()
            self.win.flip()
            if "escape" in event.waitKeys(keyList=["1", "2", "space", "enter", "return", "escape"]):
                raise KeyboardInterrupt

    def _summary(self):
        """Print accuracy, timeouts, and upper-press rate per cell (and the practice criterion)."""

        trials = pd.DataFrame([r for r in self.rows if r["trial_type"] != "cue"])
        if trials.empty:
            return
        by_cell = trials.groupby("trial_type").agg(
            accuracy=("response_correct", "mean"), timeouts=("response_timeout", "mean"), n=("trial_idx", "size")
        )
        print(by_cell.round(3).to_string())
        print(f"upper presses: {(trials.response_key == cfg.BUTTON_UPPER).mean():.3f}")
        print(
            f"max flip lag: {trials.max_flip_lag.max() * 1000:.1f} ms; dropped frames: {trials.n_dropped_frames.sum()}"
        )
        if self.practice:
            by_rule = trials.groupby("rule").response_correct.mean()
            passed = bool((by_rule >= cfg.LOC_PRACTICE_CRITERION).all() and len(by_rule) == 2)
            print(
                f"practice accuracy by rule: {by_rule.round(3).to_dict()} -> {'PASS' if passed else 'REPEAT PRACTICE'}"
            )

    def run(self):
        """Wait for the trigger, play every event at its planned onset, and save throughout."""

        status = "aborted"
        try:
            if self.practice or self.acquisition == 1:
                self.show_instructions()
            if not self.practice:
                self.show_instructions(cfg.LOC_RUN_INTRO[self.p_info["language"]][self.p_info["task"]])
            self._write_sidecar(status="started")
            self.scanner.wait_for_start()
            self.logger.start()
            events = self.design.sort_values("onset", kind="stable").to_dict("records")
            for ev in events:
                {"fixation": self._rest, "cue": self._cue, "trial": self._trial}[ev["event_type"]](ev)
            self._wait_until(float(events[-1]["onset"] + events[-1]["duration"]))
            status = "complete"
            self._summary()
            self.stim["instr"].text = cfg.LOC_END_TEXT[self.p_info["language"]]
            self.stim["instr"].draw()
            self.win.flip()
            core.wait(3.0)
        except KeyboardInterrupt:
            logging.warning("run aborted with Escape")
        finally:
            self._close(status)

    def _close(self, status="aborted"):
        """Save events and the sidecar, then close the window."""

        try:
            if self.rows:
                self._save_events()
                self._write_sidecar(
                    status=status,
                    end_time=self.logger.clock.getTime(),
                    n_dropped_frames=self.win.nDroppedFrames if self.win else None,
                )
        except (OSError, ValueError, TypeError, KeyError) as error:  # keep closing even if saving fails
            logging.error(f"failed to save data: {error}")
        if self.win:
            win, self.win = self.win, None
            win.close()
        core.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="relsem / reldist localizer runner")
    parser.add_argument("--subject", "-p", required=True)
    parser.add_argument("--session", "-s", type=int, required=True)
    parser.add_argument("--task", "-t", choices=cfg.LOC_TASKS)
    parser.add_argument("--run", "-r", type=int, default=0)
    parser.add_argument("--language", "-l", default="korean")
    parser.add_argument(
        "--mode",
        "-m",
        default=None,
        choices=["Scan", "Test"],
        help="Scan waits for scanner trigger 's' (default for runs); Test starts on Enter (default for --practice)",
    )
    parser.add_argument("--practice", action="store_true", help="run the out-of-scanner practice design with feedback")
    parser.add_argument("--screen", type=int, default=1, help="display screen index (default: 1, use 0 on single-monitor PC)")
    args = parser.parse_args()
    if not args.practice and (args.task is None or args.run < 1):
        parser.error("--task and --run (1, 2, ...) are required unless --practice")
    mode = args.mode if args.mode is not None else ("Test" if args.practice else "Scan")
    LocalizerExperiment(
        args.subject,
        args.session,
        args.task,
        args.run,
        args.language,
        mode,
        practice=args.practice,
        screen=args.screen,
    ).run()
