# Notirua

Turn a song into sheet music: Notirua splits audio into instruments (vocals,
drums, bass, guitar, piano, other), writes each one down as notation — with
tablature for guitar and bass — lets you transpose, and saves PDFs with the
song title and page numbers. Everything runs on your computer.

> Status: early development (see `PROGRESS.md`). Notirua runs from source on
> macOS, Windows, and Linux; ready-made installers are not published yet.

[한국어 안내는 아래에 있습니다.](#한국어)

## Requirements

- macOS 14 Sonoma or later (Apple Silicon or Intel), Windows 10/11 (x64), or
  Linux x86_64
- 8 GB RAM; about 1 GB of disk space for the app, components, and saved results
- [uv](https://docs.astral.sh/uv/getting-started/installation/) and git. uv
  installs the right Python (3.11) by itself.
- Linux only: Qt needs `libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3`
  (Debian/Ubuntu package names), and Korean, Japanese, or Chinese titles need a
  CJK font such as `fonts-noto-cjk`.

## Install

```bash
git clone https://github.com/jerry-leem/notirua.git
cd notirua
uv sync
```

## Use the app

```bash
uv run notirua
```

1. **First run: setup.** Notirua needs two components: the instrument
   separation model (246 MB, MIT) and the LilyPond score engraver (39 MB,
   GPL-3.0). The setup screen shows each one's size, source, and license.
   Check both and choose **Agree and install**. Nothing is downloaded before
   that, and the internet is not used afterwards. **Not now** keeps the app
   open with an **Install** button at the top. Without internet, use
   **Install from a bundle file…**.
2. **Choose a file.** Drop a music or video file anywhere in the window, or
   use **Choose a file…** (MP3, M4A, WAV, FLAC, OGG, AIFF, MP4 video, and
   more, up to 15 minutes).
3. **Options.** Check the title and instruments, then choose **Make sheet
   music**. Tuning, time signature, tempo, key, paper, and the language inside
   the PDF are under **More settings**; the defaults are automatic.
4. **Wait.** The progress screen shows each step and the time left. A
   4-minute song takes under a minute on a fast Mac and a few minutes on an
   ordinary laptop. **Cancel** stops within 3 seconds; finished steps are kept,
   so trying again is faster.
5. **Result.** Switch instruments with the tabs, page through the preview, and
   transpose with **−/+** or the key list (only the drawing is redone).
   **Save all** copies the PDFs to a folder without overwriting existing
   files. **MusicXML**, **MIDI**, **Save as WAV**, and **Hear each
   instrument** are at the bottom.

**Settings** changes the language, paper, and save folder, manages components,
and clears saved intermediate results. Open it with the button at the top
right or from the menu:

| | macOS | Windows / Linux |
|---|---|---|
| Settings | **Notirua → Settings…** (⌘,) | **File → Settings…** (Ctrl+,) |
| Quit | **Notirua → Quit Notirua** (⌘Q) | **File → Quit Notirua** (Ctrl+Q) |
| About and licenses | **Notirua → About Notirua** | **Help → About Notirua** |
| Open a file / Save all | **File** menu (⌘O / ⌘S) | **File** menu (Ctrl+O / Ctrl+S) |

On macOS, right-clicking the Dock icon also offers **Open a music file…** and
**Settings…**. The window title shows the version, for example
`Notirua 0.1.1`.

## Use the command line

```bash
uv run notirua setup                   # asks before downloading the components
uv run notirua setup --accept-licenses # same, without asking (automation)
uv run notirua setup --bundle components.zip   # install without internet

uv run notirua transcribe "song.m4a" --out ./out
uv run notirua transcribe "song.m4a" --out ./out --title "Spring" \
    --stems guitar,bass --transpose +2 --paper letter --musicxml --midi
uv run notirua transcribe "live.mp4" --start 30 --end 210 --out ./out

uv run notirua components              # installed components
uv run notirua cache                   # size of saved intermediate results
uv run notirua cache --clear
uv run notirua --lang ko               # open the window in Korean
uv run notirua transcribe --help       # every option
uv run notirua --version               # notirua 0.1.1
```

More `transcribe` options: `--to-key "G major"`, `--guitar-tuning drop_d`,
`--bass-tuning five_string`, `--time-signature 3/4`, `--tempo 96`,
`--key "D minor"`, `--shift-downbeat 1`, `--tab staff|tab|both`,
`--pdf-lang ko`, `--no-combined`, `--no-separate-pdfs`, `--track N`.

## Where Notirua keeps its files

| | macOS | Windows | Linux |
|---|---|---|---|
| Settings and components | `~/Library/Application Support/notirua` | `%LOCALAPPDATA%\notirua` | `~/.config/notirua`, `~/.local/share/notirua` |
| Saved intermediate results | `~/Library/Caches/notirua` | `%LOCALAPPDATA%\notirua\Cache` | `~/.cache/notirua` |
| Logs (for bug reports) | `~/Library/Logs/notirua` | `%LOCALAPPDATA%\notirua\Logs` | `~/.local/state/notirua/log` |

To remove Notirua, delete the cloned folder and these folders.

## Version

Notirua uses [Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`.
The current version is **0.1.1**. While the major version is 0, a minor
release may still change behavior. `uv run notirua --version` prints it, and
`CHANGELOG.md` lists what changed in each release.

## Develop

```bash
uv run pytest -m "not slow"     # fast offline tests, GUI included
uv run pytest -m slow           # end-to-end tests with the real components
uv run ruff check . && uv run ruff format --check . && uv run mypy src/notirua
```

`AGENTS.md` lists every development command.

## 한국어

Notirua는 음원 파일을 넣으면 악기별(보컬, 드럼, 베이스, 기타, 피아노, 기타 소리)로
나누고, 악보와 기타·베이스 TAB 악보를 만들어 곡명과 페이지 번호가 들어간 PDF로
저장하는 데스크톱 앱입니다. 모든 처리는 내 컴퓨터에서 이루어집니다.

> 현재 개발 초기 단계입니다(`PROGRESS.md` 참고). macOS, Windows, Linux에서 소스로
> 실행할 수 있고, 설치 파일은 아직 배포하지 않습니다.

### 필요한 것

- macOS 14 Sonoma 이상(Apple Silicon, Intel), Windows 10/11(x64), Linux x86_64
- RAM 8GB, 디스크 약 1GB(앱, 구성요소, 중간 결과)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)와 git. Python 3.11은
  uv가 알아서 설치합니다.
- Linux만: Qt용 `libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3`(Debian/Ubuntu
  패키지 이름), 한·중·일 곡명을 위한 CJK 글꼴(예: `fonts-noto-cjk`)

### 설치

```bash
git clone https://github.com/jerry-leem/notirua.git
cd notirua
uv sync
```

### 앱 사용법

```bash
uv run notirua
```

1. **처음 실행: 구성요소 설치.** 악기 분리 모델(246MB, MIT)과 악보 조판기
   LilyPond(39MB, GPL-3.0)가 필요합니다. 화면에 크기, 출처, 라이선스가 나옵니다.
   두 항목을 체크하고 **동의하고 설치**를 누르세요. 누르기 전에는 아무것도 내려받지
   않으며, 설치 후에는 인터넷을 쓰지 않습니다. **나중에**를 누르면 앱은 그대로
   열려 있고 위쪽에 **설치하기** 버튼이 남습니다. 인터넷이 없으면 **묶음 파일로
   설치…**를 쓰세요.
2. **파일 선택.** 창 아무 곳에나 음악·동영상 파일을 끌어다 놓거나 **파일 고르기…**를
   누르세요(MP3, M4A, WAV, FLAC, OGG, AIFF, MP4 동영상 등, 15분 이하).
3. **옵션.** 곡명과 악기를 확인하고 **악보 만들기**를 누르세요. 줄 맞춤, 박자,
   빠르기, 조성, 용지, PDF 언어는 **세부 설정** 안에 있고 기본값은 자동입니다.
4. **기다리기.** 단계별 상태와 남은 시간이 보입니다. 4분 곡은 빠른 Mac에서 1분
   이내, 보통 노트북에서 몇 분 걸립니다. **취소**는 3초 안에 멈추고, 끝난 단계는
   남겨 두어 다시 시도할 때 빨라집니다.
5. **결과.** 탭으로 악기를 바꾸고, 미리보기 쪽을 넘기고, **−/+** 또는 조 목록으로
   전조합니다(악보만 다시 그립니다). **모두 저장**은 기존 파일을 덮어쓰지 않고
   PDF를 폴더에 복사합니다. 아래쪽에 **MusicXML**, **MIDI**, **WAV로 저장**,
   **악기별 소리 듣기**가 있습니다.

**설정**에서 언어, 용지, 저장 폴더를 바꾸고 구성요소를 관리하며 중간 결과를 비울
수 있습니다. 오른쪽 위 버튼이나 메뉴로 엽니다.

| | macOS | Windows / Linux |
|---|---|---|
| 설정 | **Notirua → 설정…** (⌘,) | **파일 → 설정…** (Ctrl+,) |
| 종료 | **Notirua → Notirua 종료** (⌘Q) | **파일 → Notirua 종료** (Ctrl+Q) |
| 정보와 라이선스 | **Notirua → Notirua 정보** | **도움말 → Notirua 정보** |
| 파일 열기 / 모두 저장 | **파일** 메뉴 (⌘O / ⌘S) | **파일** 메뉴 (Ctrl+O / Ctrl+S) |

macOS에서는 Dock 아이콘을 오른쪽 클릭해도 **음악 파일 열기…**와 **설정…**이 나옵니다.
창 제목에 버전이 표시됩니다(예: `Notirua 0.1.1`).

### 버전

시맨틱 버전(`MAJOR.MINOR.PATCH`)을 따릅니다. 현재 버전은 **0.1.1**이며, 1.0 전까지는
MINOR 버전에서도 동작이 바뀔 수 있습니다. `uv run notirua --version`으로 확인하고, 바뀐
내용은 `CHANGELOG.md`에 적습니다.

### 명령줄 사용법

```bash
uv run notirua setup                   # 동의를 물은 뒤 구성요소 설치
uv run notirua setup --bundle components.zip   # 인터넷 없이 설치
uv run notirua transcribe "곡.m4a" --out ./out --transpose +2 --musicxml --midi
uv run notirua --lang ko transcribe --help     # 모든 옵션 (한국어)
uv run notirua --lang ko               # 한국어로 창 열기
```

파일이 저장되는 위치와 지우는 방법은 위의 "Where Notirua keeps its files" 표를
참고하세요.

## License

Notirua is released under the MIT License (`LICENSE`). Components it bundles or
downloads keep their own licenses (`docs/LICENSES.md`).
Notirua는 MIT 라이선스로 배포합니다.

## Documents

- `SPEC.md` — requirements (Korean) · `AGENTS.md` — contributor/agent guide
- `PROGRESS.md` — current status and next steps
- `docs/DECISIONS.md` — measurements and decisions · `docs/LICENSES.md` — third-party licenses
- `docs/TRANSLATING.md` — how to add a language
