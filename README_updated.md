# How to run

## main experiment (run 1 to run 10)
### 1. Setup conda environment
```bash
conda activate fv-main   # name is set inside environment.yml
```

### 2. Run experiments
```bash
cd Desktop/Declan/MainExp

# Run a single run (Korean, scanner mode)
python run_experiment.py -p 01 -s 1 -r 1

# Run in test mode (no scanner trigger needed — press Enter to start)
python run_experiment.py -p 01 -s 1 -r 1 --mode Test
```

## Experiment Structure

- **8 subjects** × **8 sessions** × **10 runs per session** = 80 runs total per subject
- Each run has **25 blocks**: 20 relation blocks + 5 baseline (fixation) blocks
- 64 unique semantic relations, drawn from a farthest-point sampling of the SemEval-2012 relation set
- Counterbalancing ensures no pair of relations co-occurs together in more than 1 run

### Block Structure (Relation Blocks)

1. **4 example pairs** shown sequentially (word1 alone → word1 : word2)
2. **1 probe trial**: word1 alone → 2AFC (word1 + two vertically arranged options)
3. Participant selects upper or lower option via button press

### Baseline Blocks

- **Default (`--baseline fixation`)**: fixation cross for 12 s
- **Structured (`--baseline structured`)**: same timing/layout as relation blocks but with placeholder word pairs (configurable in `config.py`)

## Command-Line Arguments

| Argument | Short | Default | Description |
|---|---|---|---|
| `--subject` | `-p` | *(required)* | Subject ID (e.g., `01`) |
| `--session` | `-s` | *(required)* | Session number (1–8) |
| `--run` | `-r` | *(required)* | Run number (1–10) |
| `--language` | `-l` | `korean` | Stimulus language (`korean` or `english`) |
| `--mode` | `-m` | `Scan` | `Scan` (waits for scanner trigger) or `Test` (press Enter to start) |
| `--baseline` | `-b` | `fixation` | Baseline block type: `fixation` or `structured` |
| `--fixed-block-duration` | | `False` | If set, pad each block to 12 s with fixation before starting the next block (see below) |

## Block Timing Modes

### Default: immediate proceed

By default, the next block starts **immediately** after the participant responds to the probe trial. This means block durations are self-paced and variable — fast responses yield shorter blocks (~8–9 s), slow responses yield longer blocks (potentially >12 s). Combined with the TR/block misalignment (see below), this provides additional temporal jittering at the block level.

```bash
python run_experiment.py -p 01 -s 1 -r 1
```

### Fixed block duration (`--fixed-block-duration`)

When this flag is set, each block is padded with fixation to a minimum of 12 s (`BLOCK_DURATION` in `config.py`). If the participant's response already exceeded 12 s, the next block proceeds immediately. This gives uniform block durations for most trials.

```bash
python run_experiment.py -p 01 -s 1 -r 1 --fixed-block-duration
```

## TR and Temporal Jittering

The scanner TR is **1.4 s** (configurable in `config.py`). Since 12 s blocks do not divide evenly by 1.4 s (12 / 1.4 ≈ 8.57 TRs), block boundaries naturally misalign with volume acquisitions across successive blocks. This provides implicit temporal jittering without requiring explicit jitter parameters — the BOLD sampling effectively shifts relative to block onsets across the run.

## Key Configuration Parameters (`config.py`)

These are the parameters most likely to need adjustment for your setup:

| Parameter | Default | Description |
|---|---|---|
| `EXAMPLE_DURATION` | `1.5` | Total display time per example pair (s) |
| `WORD_DURATION` | `0.75` | Each word shown for half the pair duration (s) |
| `ISI` | `0.25` | Inter-stimulus interval between pairs (s) |
| `BLOCK_DURATION` | `12.0` | Target block duration (s); only enforced when `--fixed-block-duration` is set |
| `TR_DURATION` | `1.4` | Scanner TR (s) |
| `BUTTON_UPPER` | `'1'` | Button box key for upper option |
| `BUTTON_LOWER` | `'4'` | Button box key for lower option |
| `FONT_NAME_KOREAN` | `'AppleGothic'` | Korean font; change for non-macOS systems |
| `FONT_NAME` | `'Courier New'` | Default monospace font (English/fixation) |

## Output

Output follows BIDS format and is saved to `output/`:

```
output/
├── sourcedata/          # pre-generated design matrices (do not modify)
│   └── sub-XX/ses-XX/
│       └── sub-XX_ses-XX_task-analogyKorean_run-XX_design.csv
└── sub-XX/ses-XX/func/
    ├── sub-XX_ses-XX_task-analogyKorean_run-XX_events.tsv   # trial-level events
    ├── sub-XX_ses-XX_task-analogyKorean_run-XX_events.json  # BIDS sidecar
    └── experiment.log                                        # detailed timing log
```

The `_events.tsv` file contains one row per block with columns: `onset`, `duration`, `trial_type` (relation name or `baseline`), `trial_idx`, `response_time`, `response_correct`, `response_chosen`, `correct_answer`.

Run accuracy (excluding baseline) is printed to the console at the end of each run for the experimenter.

## Platform Notes

- **macOS**: should work out of the box with the default `AppleGothic` Korean font.
- **Windows/Linux**: update `FONT_NAME_KOREAN` in `config.py` to a monospace Korean font available on the system (e.g., `'Malgun Gothic'` on Windows).
- The experiment has been tested with **PsychoPy 2025.1.1** (Python 3.10). See `requirements.txt` for full dependencies.
