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
