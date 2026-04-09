"""
Utility functions for fMRI Analogy Experiment.
"""
import json
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
from psychopy import core, event, logging, visual
from config import OUTPUT_DIR, SOURCEDATA_DIR, TASK_NAME_BASE

@dataclass
class Block:
    block_idx: int
    block_type: str
    
    # For relation blocks
    examples: list[tuple[str, str]] = None
    probe: dict = None
    relation_name: str = None
    relation_category: str = None
    
    @property
    def trial_type(self) -> str:
        return self.relation_name if self.block_type == 'relation' else self.block_type

class Scanner:
    """
    Handles MRI synchronization for both Real (key-based) and Test (clock-based) modes.
    Ensures trial onsets align to TR grid even if experiment lags.
    """
    def __init__(self, win, mode='Scan', tr=1.5, sync_key='5', font='Arial'):
        self.win = win
        self.mode = mode
        self.tr = tr
        self.sync_key = sync_key
        self.font = font
        self.clock = core.Clock() 
        self.vol_index = 0
        self.start_time = None
        
    def wait_for_start(self):
        """Blocks until first sync pulse (Scan) or manual trigger (Test)."""
        # Explicit instructions for the user
        action = "Press [ENTER] to start simulation" if self.mode == 'Test' else f"Waiting for scanner trigger ('{self.sync_key}')..."
        msg = f"Mode: {self.mode}\nTR: {self.tr}s\n\n{action}"
        
        # Use height units (0.03 = 3% screen height) for consistent readability
        txt = visual.TextStim(self.win, text=msg, font=self.font, 
                            color='white', height=0.03, units='height')
        
        event.clearEvents()
        while True:
            txt.draw()
            self.win.flip()
            keys = event.getKeys()
            
            # Aggressive exit check
            if 'escape' in keys:
                self.win.close()
                core.quit()
            
            # Test: Allow Enter/Return/Space to start
            if self.mode == 'Test' and any(k in keys for k in ['return', 'enter', 'space']):
                break
            # Scan: Only specific sync key starts
            if self.mode == 'Scan' and self.sync_key in keys:
                break
                
        self.start_time = self.clock.getTime()
        self.clock.reset() # 0.0 is now the first TR
        self.vol_index = 0
        
        # Log the "start" TR immediately
        self._log_tr(0.0, sim=(self.mode == 'Test'))
        self.vol_index = 1 
        logging.exp(f"Scanner started in {self.mode} mode")
        
    def check_for_tr(self):
        """Non-blocking check to log TRs during active tasks (e.g. 2AFC)."""
        if self.mode == 'Test':
            now = self.clock.getTime()
            # Catch up on any TRs we passed while doing other things
            while (self.vol_index * self.tr) <= (now + 0.005):
                t = self.vol_index * self.tr
                self._log_tr(t, sim=True)
                self.vol_index += 1
        else:
            # Check buffer for physical keys
            for _, t in event.getKeys(keyList=[self.sync_key], timeStamped=self.clock):
                self._log_tr(t, sim=False)

    def wait_for_next_tr(self):
        """
        Blocks execution until the NEXT future TR boundary.
        """
        # Always check for quit first
        if event.getKeys(keyList=['escape']):
            self.win.close()
            core.quit()

        if self.mode == 'Test':
            now = self.clock.getTime()
            
            # 1. Fast-forward: Acknowledge any TRs we already missed
            while (self.vol_index * self.tr) <= (now + 0.001):
                t = self.vol_index * self.tr
                self._log_tr(t, sim=True)
                self.vol_index += 1
            
            # 2. Wait: Target the next FUTURE TR
            next_tr_time = self.vol_index * self.tr
            delay = next_tr_time - self.clock.getTime()
            
            if delay > 0:
                core.wait(delay, hogCPUperiod=delay)
            
            # 3. Log the TR we just waited for
            self._log_tr(next_tr_time, sim=True)
            self.vol_index += 1
            
        else:
            # Real Scanner: Just block for the key
            event.clearEvents(eventType='keyboard')
            while True:
                # Still check escape while waiting for scanner
                if event.getKeys(keyList=['escape']):
                    self.win.close()
                    core.quit()
                    
                keys = event.getKeys(keyList=[self.sync_key], timeStamped=self.clock)
                if keys:
                    self._log_tr(keys[0][1], sim=False)
                    return
                core.wait(0.001)

    def _log_tr(self, t, sim):
        logging.data(f"TR at {t:.4f}s {'(Simulated)' if sim else ''}")

class EventLogger:
    """Logs trial events in BIDS-compliant format."""
    def __init__(self):
        self.trials = []
        self._clock = core.Clock()
    
    @property
    def clock(self): return self._clock

    def start(self): self._clock.reset()

    def log_trial(self, **kwargs):
        self.trials.append(kwargs)
    
    def get_dataframe(self):
        return pd.DataFrame(self.trials)

# --- Helpers ---

def _bids_task(language):
    return f"{TASK_NAME_BASE}{language.capitalize()}"

def _bids_prefix(subject, session, run, language):
    sub_id = f"sub-{int(subject):02d}"
    ses_id = f"ses-{session:02d}"
    run_id = f"run-{run:02d}"
    return sub_id, ses_id, f"{sub_id}_{ses_id}_task-{_bids_task(language)}_{run_id}"

def load_run_data(language, subject, session, run):
    sub_id, ses_id, prefix = _bids_prefix(subject, session, run, language)
    path = (Path(__file__).parent / OUTPUT_DIR / SOURCEDATA_DIR
            / sub_id / ses_id / f"{prefix}_design.csv")
    if not path.exists(): raise FileNotFoundError(f"Missing data: {path}")
    
    df = pd.read_csv(path)
    blocks = []
    for tidx, grp in df.groupby('trial_idx'):
        row = grp.iloc[0]
        if row['trial_type'] == 'baseline':
            blocks.append(Block(block_idx=tidx, block_type='baseline'))
            continue

        examples = [(r['word1'], r['word2']) for _, r in grp[grp['trial_type'] == 'example'].iterrows()]
        p = grp[grp['trial_type'] == 'probe'].iloc[0]
        blocks.append(Block(
            block_idx=tidx, block_type='relation', examples=examples,
            probe=dict(word1=p['word1'], target=p['word2'],
                       opt1=p['option_1'], opt2=p['option_2'],
                       corr_ans=p['correct_response']),
            relation_name=row['relation_name'],
            relation_category=row['relation_category'],
        ))

    blocks.sort(key=lambda b: b.block_idx)
    return blocks

def create_output_directory(subject, session, run, language):
    sub_id, ses_id, _ = _bids_prefix(subject, session, run, language)
    out = Path(__file__).parent / OUTPUT_DIR / sub_id / ses_id / "func"
    out.mkdir(parents=True, exist_ok=True)
    return out

def save_experiment_data(output_dir, event_logger, subject, session, run, language, *, run_ts, **kwargs):
    """Saves event data to BIDS-compliant TSV/JSON."""
    df = event_logger.get_dataframe()
    if df.empty:
        logging.warning("No data collected to save.")
        return

    bids_cols = ['onset', 'duration', 'trial_type', 'trial_idx']
    cols = [c for c in bids_cols if c in df.columns] + [c for c in df.columns if c not in bids_cols]

    _, _, prefix = _bids_prefix(subject, session, run, language)
    stem = f"{prefix}_events_{run_ts}"
    tsv_path = output_dir / f"{stem}.tsv"
    df[cols].to_csv(tsv_path, sep='\t', index=False, na_rep='n/a')

    sidecar = {
        "onset": {"Units": "s"}, "duration": {"Units": "s"},
        "trial_type": {"Description": "Relation name"},
        "response_time": {"Units": "s"},
        "response_correct": {"Description": "True if subject selected correct option"}
    }
    with open(output_dir / f"{stem}.json", 'w') as f:
        json.dump(sidecar, f, indent=2)

    acc = df['response_correct'].mean() * 100 if 'response_correct' in df else 0
    logging.info(f"Saved {len(df)} events to {tsv_path.name}. Accuracy: {acc:.1f}%")

def generate_jittered_iti(min_t=4.0, max_t=8.0, mean_t=6.0):
    rate = 1.0 / (mean_t - min_t)
    while True:
        iti = min_t + np.random.exponential(1.0 / rate)
        if iti <= max_t: return iti