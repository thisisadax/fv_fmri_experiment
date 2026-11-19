"""
Configuration settings for the fMRI Analogy Experiment.

Contains timing, display, button mappings, and scanner parameters.
"""

# Timing (seconds)
N_EXAMPLES_PER_BLOCK = 4
N_PROBES_PER_BLOCK = 1
EXAMPLE_DURATION = 2.0 
WORD_DURATION = EXAMPLE_DURATION / 2  # each word shown for half the pair duration
ISI = 0.0  # ISI between successive examples/probes
BLOCK_DURATION = 12.0
TR_DURATION = 1.4
MAX_RESPONSE_TIME = 4.0

BASELINE_BLOCK_TYPE = "baseline"

# Word pairs for the structured baseline condition (per language).
# Each baseline block presents these 4 example pairs followed by a 2AFC probe, using the same timing/layout as relation blocks.
BASELINE_TRIALS = {
    'english': {
        'examples': [('word1', 'word2'), ('word3', 'word4'), ('word5', 'word6'), ('word7', 'word8')],
        'probe': {'word1': 'word9', 'option_1': 'word10', 'option_2': 'word9'},
    },
    'korean': {
        'examples': [('단어1', '단어2'), ('단어3', '단어4'), ('단어5', '단어6'), ('단어7', '단어8')],
        'probe': {'word1': '단어9', 'option_1': '단어10', 'option_2': '단어9'},
    },
}

# Scanner settings (for psychopy-mri-emulator)
SCANNER_SETTINGS = {
    'TR': TR_DURATION,      # seconds between volume acquisitions
    'volumes': 220,         # 25 blocks x 12s = 300s; 300/1.4 ≈ 215 TRs + buffer
    'sync': 's',            # key used as sync pulse
    'skip': 0,              # volumes to skip during T1 stabilization
    'sound': False          # don't simulate scanner noise
}

# Response keys
QUIT_KEYS = ['escape']
BUTTON_UPPER = '1'
BUTTON_LOWER = '2'
RESPONSE_KEYS = [BUTTON_UPPER, BUTTON_LOWER]

# Display
WINDOW_SIZE = [1920, 1080]
FULLSCREEN = True
MONITOR_NAME = 'testMonitor'
UNITS = 'deg'

BACKGROUND_COLOR = [0, 0, 0]
TEXT_COLOR = 'black'
FIXATION_COLOR = 'white'

WORD_HEIGHT = 1.0
INSTRUCTION_HEIGHT = 1.0
INSTRUCTION_WRAP_WIDTH = 45
FIXATION_SIZE = 1.0

# Text formatting
COLON_SPACING = " "

# AFC Layout
AFC_OPTION_Y = 1.0  # Vertical offset for upper/lower options
AFC_OPTION_HEIGHT = 1.2

# Font (language-specific)
FONT_NAME = 'Courier New'
FONT_NAME_KOREAN = 'Malgun Gothic'  # macOS font that works well for Korean text; fallback to system if unavailable

# Data paths (BIDS format)
OUTPUT_DIR = "output"
SOURCEDATA_DIR = "sourcedata"

# BIDS settings
TASK_NAME_BASE = "analogy"

# Instructions
INSTRUCTIONS = {
    'english': """
Welcome to the experiment!

In this task, you will see blocks of word pairs followed by a test question, interspersed with short rest periods.

For each block:
1. You will see word pairs presented in sequence.
2. Then, you will see a word with two options.
3. Please select the option you feel is the best match for the relationship shared by the previous pairs. Answer to the best of your ability.

Press the UPPER button for the upper option.
Press the LOWER button for the lower option.

During rest periods, please relax, clear your mind, and maintain your focus on the central cross.

The experiment will begin shortly.
""",
    'korean': """
실험에 오신 것을 환영합니다!

이 과제에서는 단어 쌍 블록 다음에 테스트 질문이 이어지며, 짧은 휴식 기간이 중간에 포함됩니다.

각 블록에서:
1. 단어 쌍들이 순서대로 제시됩니다.
2. 그런 다음, 한 단어와 두 개의 선택지를 보게 됩니다.
3. 이전 쌍들이 공유하는 관계와 가장 일치한다고 생각되는 선택지를 선택해 주세요. 최선을 다해 응답해 주시면 됩니다.

위쪽 옵션은 1번 버튼을 누르세요.
아래쪽 옵션은 2번 버튼을 누르세요.

휴식 기간 동안에는 긴장을 풀고, 마음을 비우고, 중앙의 십자가에 시선을 고정해 주세요.

곧 실험이 시작됩니다.
"""
}

WAIT_FOR_SCANNER_TEXT = {
    'english': "Waiting for scanner...",
    'korean': "스캐너 대기 중..."
}

END_TEXT = {
    'english': "Run complete. Thank you!",
    'korean': "실행 완료. 감사합니다!"
}

CONTINUE_HINT_TEXT = {
    'english': "(press any button to continue)",
    'korean': "(계속하려면 아무 버튼이나 누르세요)"
}


# ---------------------------------------------------------------------------
# Relational localizers (tasks relsem and reldist; run_localizer.py)
# ---------------------------------------------------------------------------

LOC_TASKS = ("relsem", "reldist")  # relational vs semantic completion; relational near vs far
LOC_PRACTICE_TASK = "relloc"  # practice design name (both tasks' cells, with feedback)
LOC_N_VOLUMES = 215  # 296 s run = 212 volumes at TR 1.4 s, plus 3 spare
LOC_TRIAL_SCREENS = {"fixation": 0.25, "word_a": 0.50, "pair": 1.25, "word_c": 0.50, "options": 3.00, "post": 0.50}
LOC_FLIP_LEAD = 0.008  # request each flip this long before its planned onset (half a 60 Hz frame)
LOC_PRACTICE_CRITERION = 0.80  # scan only after this practice accuracy under both rules

LOC_RULE_CUES = {"korean": {"rel": "관계", "sem": "의미"}, "english": {"rel": "RELATION", "sem": "MEANING"}}
LOC_CUE_HEIGHT = 1.6  # deg, rule word on the 2 s cue screen
LOC_RULE_LABEL_HEIGHT = 0.7  # deg, rule word kept above the trial display
LOC_RULE_LABEL_Y = 3.5  # deg
LOC_RULE_LABEL_COLOR = [0.4, 0.4, 0.4]

LOC_FEEDBACK_TEXT = {
    "korean": {"correct": "정답", "incorrect": "오답", "timeout": "시간 초과"},
    "english": {"correct": "Correct", "incorrect": "Incorrect", "timeout": "Too slow"},
}
LOC_FEEDBACK_COLORS = {"correct": [-1, 0.4, -1], "incorrect": [0.6, -1, -1], "timeout": "black"}

LOC_RUN_INTRO = {
    "korean": {
        "relsem": "이번 런에서는 '관계' 블록과 '의미' 블록이 번갈아 나옵니다.\n\n각 블록 처음에 나오는 규칙 단어를 확인하세요.",
        "reldist": "이번 런에서는 모든 블록이 '관계' 블록입니다.\n\nA 와 B 의 관계를 C 에 적용해 단어를 고르세요.",
    },
    "english": {
        "relsem": "In this run, RELATION and MEANING blocks alternate.\n\nCheck the rule word at the start of each block.",
        "reldist": "In this run, every block is a RELATION block.\n\nApply the A : B relation to C to choose the word.",
    },
}

LOC_INSTRUCTIONS = {
    "korean": """
이 과제에서는 블록마다 주어지는 규칙에 따라 단어를 고릅니다.

각 블록은 규칙 단어로 시작하며, 규칙 단어는 블록이 끝날 때까지 화면 위쪽에 표시됩니다.

먼저 단어 쌍 A : B 가 나오고, 이어서 단어 C 와 두 개의 선택지가 나옵니다.

'관계' 블록: A 와 B 의 관계를 생각한 뒤, C 와 같은 관계를 이루는 단어를 고르세요.

'의미' 블록: A : B 와 상관없이, C 와 의미가 가장 가까운 단어를 고르세요.

위쪽 단어는 1번 버튼, 아래쪽 단어는 2번 버튼을 누르세요. 선택지가 사라지기 전에 정확하고 빠르게 응답해 주세요.

십자가가 보이면 십자가를 바라보며 쉬어 주세요.
""",
    "english": """
In this task you choose words by the rule shown at the start of each block.

The rule word stays at the top of the screen until the block ends.

First a word pair A : B appears, then a word C with two options.

RELATION blocks: think about how A and B are related, then choose the word that relates to C in the same way.

MEANING blocks: regardless of A : B, choose the word closest in meaning to C.

Press the UPPER button for the upper word and the LOWER button for the lower word. Answer accurately and quickly, before the options disappear.

When you see the cross, rest and look at the cross.
""",
}

LOC_END_TEXT = {"korean": "이번 런이 끝났습니다. 감사합니다!", "english": "Run complete. Thank you!"}
