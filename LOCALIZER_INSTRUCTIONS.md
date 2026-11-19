# 관계 국소화 과제 실행 안내 / Relational Localizer Run Guide (`relsem` & `reldist`)

모국어 화자 검토가 반영된 한국어 관계 국소화 과제(`relsem`, `reldist`) 실행 패키지입니다.
본 과제(`run_experiment.py`)와 **동일한 스캐너 트리거(`s`), 버튼(`1` = 위쪽, `2` = 아래쪽), TR(`1.4 s`), 화면·폰트 설정(`Malgun Gothic`)** 을 그대로 사용합니다.

*(English instructions follow the Korean section below.)*

---

## 한국어 안내 (Korean)

### 1. 준비된 참가자 및 세션 (동일 자극 시퀀스 사전 생성 완료)

`sub-01`과 `sub-03` 모두 동일한 자극·블록 순서(`seed = 1001`)로 설계 파일이 미리 생성되어 있습니다.

| 참가자 | 세션 인자 | 설계 파일 경로 (`output/sourcedata/...`) | 비고 |
|---|---|---|---|
| **sub-01** | `-p 01 -s 10` | `output/sourcedata/sub-01/ses-10/` | `ses-01..09` 이후 세션 |
| **sub-03** | `-p 03 -s 9` *(또는 `-s 10`)* | `output/sourcedata/sub-03/ses-09/` 및 `ses-10/` | `ses-09`와 `ses-10` 둘 다 동일하게 준비되어 있으므로 스캐너 세션 번호에 맞춰 사용하세요 |

### 2. 스캐너 및 하드웨어 설정 (본 과제와 동일)

- **시퀀스 / TR:** 본 과제와 동일한 7T EPI (`TR = 1.4 s`)
- **런당 볼륨 수 (Measurements):** **`215` 볼륨** (`301.0초`; 실제 과제는 첫 트리거 기준 정확히 **`296.0초`** = `211.4 TR`에 종료되며 약 3볼륨 여유 포함)
- **총 런 수:** 본 과제 **8런** (`relsem` 4런 + `reldist` 4런 교대 실행, 총 기능적 스캔 약 40분) + 스캐너 밖 연습 1회(약 4분)
- **스캐너 트리거 키:** `s` (본 과제 `config.py`와 동일)
- **반응 버튼:** `1` = 위쪽 선택지, `2` = 아래쪽 선택지, `Esc` = 강제 종료(그때까지의 기록 자동 저장)

### 3. 스캔 전 자극 제시 컴퓨터 점검 (약 2분)

자극 제시 컴퓨터에서 본 과제와 동일한 PsychoPy 환경(`PsychoPy 2025.1.1`, `Python 3.10`; 필요 시 `conda env create -f environment_win.yml`)을 활성화한 뒤, 이 폴더에서 아래 명령으로 점검합니다:

```bash
python run_localizer.py -p 01 -s 10 -t relsem -r 1 --mode Test
```

- 지시문 화면에서 `1`, `2`, `Space`, `Enter` 중 하나를 눌러 넘긴 뒤, 대기 화면에서 `Enter`를 누르면 시작됩니다.
- **확인 사항:** (1) 한글(`맑은 고딕`)과 콜론(`:`) 정렬이 정상인지, (2) 화면 상단 회색 규칙 단어(`관계` / `의미`)가 잘 보이는지, (3) `1`번·`2`번 버튼 입력이 반응하는지 확인 후 `Esc`로 종료해도 됩니다.
- 모니터가 1대뿐인 PC에서 테스트할 때는 `--screen 0` 옵션을 추가하세요(기본값 `--screen 1`은 본 과제와 동일한 스캐너 프로젝터 화면입니다).

### 4. 스캔 당일 실행 순서

#### (1) 스캐너 밖 연습 과제 (약 4분 / 256초, 정답·오답 피드백 제공)

`--practice`는 기본적으로 `Test` 모드로 열리므로 트리거(`s`) 없이 대기 화면에서 **`Enter`** 를 누르면 바로 시작됩니다.

```bash
# sub-01 연습
python run_localizer.py -p 01 -s 10 --practice

# sub-03 연습 (세션 번호가 9면 -s 9, 10이면 -s 10)
python run_localizer.py -p 03 -s 9 --practice
```

- 종료 후 콘솔에 `관계`(`rel`)와 `의미`(`sem`) 두 규칙 모두 정확도 **80% 이상**이면 `PASS`가 출력됩니다.
- `REPEAT PRACTICE`가 뜨면 동일한 명령으로 연습을 한 번 더 진행해 주세요.

#### (2) 스캐너 본 과제 8런 (각 런 `296초`, 스캐너 볼륨 **`215`개** 요청, `TR = 1.4 s`)

반드시 아래 순서(`relsem`과 `reldist` 교대)대로 실행해 주세요.
전체 지시문은 첫 번째 런(`relsem -r 1`) 앞에서만 나오며, 각 런 시작 전 짧은 안내 화면에서 버튼을 누르면 `Waiting for scanner trigger ('s')...` 화면으로 넘어간 뒤 **첫 번째 `s` 트리거**와 함께 시작됩니다.

**`sub-01` (`ses-10`):**
```bash
python run_localizer.py -p 01 -s 10 -t relsem -r 1
python run_localizer.py -p 01 -s 10 -t reldist -r 1
python run_localizer.py -p 01 -s 10 -t relsem -r 2
python run_localizer.py -p 01 -s 10 -t reldist -r 2
python run_localizer.py -p 01 -s 10 -t relsem -r 3
python run_localizer.py -p 01 -s 10 -t reldist -r 3
python run_localizer.py -p 01 -s 10 -t relsem -r 4
python run_localizer.py -p 01 -s 10 -t reldist -r 4
```

**`sub-03` (`ses-09` 기준; `ses-10`으로 스캔할 경우 `-s 9`를 `-s 10`으로 변경):**
```bash
python run_localizer.py -p 03 -s 9 -t relsem -r 1
python run_localizer.py -p 03 -s 9 -t reldist -r 1
python run_localizer.py -p 03 -s 9 -t relsem -r 2
python run_localizer.py -p 03 -s 9 -t reldist -r 2
python run_localizer.py -p 03 -s 9 -t relsem -r 3
python run_localizer.py -p 03 -s 9 -t reldist -r 3
python run_localizer.py -p 03 -s 9 -t relsem -r 4
python run_localizer.py -p 03 -s 9 -t reldist -r 4
```

#### (3) 결과 파일 전달

스캔 종료 후 아래 출력 폴더 전체(`func/` 및 `beh/` 포함; 파일명에 타임스탬프가 붙어 있어 덮어써지지 않음)를 연구팀에 보내 주세요:
- `output/sub-01/ses-10/`
- `output/sub-03/ses-09/` *(또는 `output/sub-03/ses-10/`)*

---

## English Instructions

### 1. Pre-Generated Participants & Sessions (Identical Stimulus Sequences)

Both `sub-01` and `sub-03` are pre-generated with the exact same reviewed Korean stimulus and block sequences (`seed = 1001`):

| Participant | CLI Flags | Design Folder (`output/sourcedata/...`) | Notes |
|---|---|---|---|
| **sub-01** | `-p 01 -s 10` | `output/sourcedata/sub-01/ses-10/` | Follows `ses-01..09` |
| **sub-03** | `-p 03 -s 9` *(or `-s 10`)* | `output/sourcedata/sub-03/ses-09/` and `ses-10/` | Both `ses-09` and `ses-10` are pre-populated identically; use whichever session number matches the MRI console |

### 2. Scanner & Hardware Settings (Identical to `run_experiment.py`)

- **Sequence / TR:** Same 7T EPI sequence as the main analogy experiment (`TR = 1.4 s`).
- **Volumes per run:** Request **`215` volumes** (`301.0 s`; the task finishes at exactly **`296.0 s`** = `211.4` TRs from the first trigger, leaving ~3 buffer volumes).
- **Trigger & Buttons:** Sync trigger = `'s'`; Upper option = `'1'`; Lower option = `'2'`; Abort = `'escape'` (saves all completed trials).
- **Timing architecture:** Every cue, word, option window (`3.0 s` deadline), and fixation period is scheduled at its exact absolute onset from the first `'s'` trigger (`0.008 s` flip lead, `callOnFlip`), so disk I/O and response times never accumulate timing drift.

### 3. Pre-Scan Stimulus-PC Check (~2 min)

Activate the PsychoPy environment (`PsychoPy 2025.1.1`, `Python 3.10`, same as `run_experiment.py`) and run from the repository root:

```bash
python run_localizer.py -p 01 -s 10 -t relsem -r 1 --mode Test
```

Advance through instructions (`1`, `2`, `Space`, or `Enter`), press `Enter` at the start screen, verify Korean rendering (`Malgun Gothic`), colon alignment, the top grey rule label (`관계` / `의미`), and `1`/`2` button presses, then press `Esc` (or let it finish at `296 s`). Use `--screen 0` if testing on a single-monitor machine (`--screen 1` is the default projector screen).

### 4. Scan-Day Commands

#### (1) Out-of-Scanner Practice (~4 min / 256 s, with trial-by-trial feedback)

`--practice` defaults to `Test` mode so you can start with **`Enter`** outside the scanner:

```bash
# sub-01
python run_localizer.py -p 01 -s 10 --practice

# sub-03 (use -s 9 or -s 10 to match your BIDS session number)
python run_localizer.py -p 03 -s 9 --practice
```

Proceed to the scanner once console output shows `PASS` (`>= 80%` accuracy on both `rel` and `sem` rules; repeat once if `REPEAT PRACTICE` is printed).

#### (2) Eight Scanner Runs in Alternating Order (`296 s` / `215` volumes each at `TR = 1.4 s`)

**`sub-01` (`ses-10`):**
```bash
python run_localizer.py -p 01 -s 10 -t relsem -r 1
python run_localizer.py -p 01 -s 10 -t reldist -r 1
python run_localizer.py -p 01 -s 10 -t relsem -r 2
python run_localizer.py -p 01 -s 10 -t reldist -r 2
python run_localizer.py -p 01 -s 10 -t relsem -r 3
python run_localizer.py -p 01 -s 10 -t reldist -r 3
python run_localizer.py -p 01 -s 10 -t relsem -r 4
python run_localizer.py -p 01 -s 10 -t reldist -r 4
```

**`sub-03` (`ses-09`; change `-s 9` to `-s 10` if scanning as session 10):**
```bash
python run_localizer.py -p 03 -s 9 -t relsem -r 1
python run_localizer.py -p 03 -s 9 -t reldist -r 1
python run_localizer.py -p 03 -s 9 -t relsem -r 2
python run_localizer.py -p 03 -s 9 -t reldist -r 2
python run_localizer.py -p 03 -s 9 -t relsem -r 3
python run_localizer.py -p 03 -s 9 -t reldist -r 3
python run_localizer.py -p 03 -s 9 -t relsem -r 4
python run_localizer.py -p 03 -s 9 -t reldist -r 4
```

#### (3) Returning Data

Send back the participant's output directory (`output/sub-01/ses-10/` and `output/sub-03/ses-09/` or `ses-10/`, including both `func/` and `beh/`).

### 5. Regenerating Designs for Another Subject or Session (Optional)

```bash
python prepare_localizer.py --items data/localizer/korean/items.tsv --subject 04 --session 9 --seed 1001 --relsem-runs 4 --reldist-runs 4 --match-columns klue_margin krsbert_margin lo_rel4 lo_syn4 d_rel_zipf zipf_diff d_rel_syllables c_zipf source_syllables source_zipf lo_prior typ_pmi --relsem-match-columns pair_sim lo_rel1 shortcut

python prepare_localizer.py --practice-items data/localizer/korean/practice_items.tsv --subject 04 --session 9 --seed 1001
```
