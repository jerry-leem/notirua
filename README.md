# Notirua (노티루아)

Notirua(노티루아)는 음원 파일을 넣으면 악기별(보컬, 드럼, 베이스, 기타, 피아노, 다른 악기)로
나누고, 악보와 기타·베이스 TAB 악보를 만들어 곡명과 페이지 번호가 들어간 PDF로
저장하는 데스크톱 앱입니다. 모든 악보 맨 위에는 코드(예: C, Am, G7)가 코드가 바뀌는
곳에만 표시됩니다. 모든 처리는 내 컴퓨터에서 이루어집니다.

[English instructions are below.](#english)

## 주요 특징

### 여러 운영체제 지원

| 운영체제 | 지원 범위 | 설치 파일 |
|---|---|---|
| macOS | 14 Sonoma 이상, Apple Silicon과 Intel | Apple Silicon용 `.dmg` (Intel용은 준비 중) |
| Windows | 10, 11 (x64) | 설치 프로그램 `.exe` |
| Linux | x86_64, glibc 2.31 이상(Ubuntu 20.04 이상 등) | `.AppImage` 하나로 실행 |

세 운영체제 모두 같은 화면과 기능을 씁니다. 메뉴와 단축키는 각 운영체제의 관례를
따릅니다(macOS는 앱 메뉴와 ⌘, Windows·Linux는 파일 메뉴와 Ctrl). 설치 파일은
Python이나 다른 프로그램을 따로 설치하지 않아도 되며, 한·중·일 곡명용 글꼴은 Linux
설치 파일에 들어 있습니다(macOS와 Windows는 시스템 글꼴을 씁니다).

### 다국어 지원

- 화면, 명령줄 도움말, 오류 메시지, Qt 기본 대화상자가 **한국어와 영어**로 나옵니다.
- 처음에는 운영체제 언어를 따르고, **설정**에서 바꾸거나 `--lang ko`, `--lang en`으로
  고를 수 있습니다(화면 언어는 다시 시작하면 적용).
- PDF 안의 글자(악기 이름, 페이지 번호 등) 언어는 화면 언어와 따로 정할 수
  있습니다(**세부 설정**, 명령줄 `--pdf-lang`).
- 곡명은 어떤 언어로 써도 PDF에 그대로 들어갑니다.
- 새 언어는 프로그램을 고치지 않고 `locales/<언어>/LC_MESSAGES/notirua.po` 번역
  파일 하나만 추가하면 됩니다(템플릿 `locales/notirua.pot`). 번역 기여를 환영합니다.

## 내려받기와 설치

최신 배포판은 [**Notirua 0.3.0 릴리스 페이지**](https://github.com/jerry-leem/notirua/releases/tag/v0.3.0)에
있습니다. 릴리스 페이지에 한국어 설치 방법, 사용법, 바뀐 점, 알려진 제한이 함께 적혀
있습니다. 지난 버전은 [모든 릴리스](https://github.com/jerry-leem/notirua/releases)에서
볼 수 있습니다.

| 컴퓨터 | 내려받기 (0.3.0) | 설치 |
|---|---|---|
| Mac (Apple Silicon), macOS 14 이상 | [Notirua-0.3.0-macos-arm64.dmg](https://github.com/jerry-leem/notirua/releases/download/v0.3.0/Notirua-0.3.0-macos-arm64.dmg) (120 MB) | 열어서 Notirua를 Applications 폴더로 끌어다 놓기 |
| Windows 10/11 (x64) | [Notirua-0.3.0-windows-x64-setup.exe](https://github.com/jerry-leem/notirua/releases/download/v0.3.0/Notirua-0.3.0-windows-x64-setup.exe) (107 MB) | 실행해서 안내에 따라 설치(관리자 권한 필요 없음) |
| Linux x86_64 (glibc 2.31 이상) | [Notirua-0.3.0-linux-x86_64.AppImage](https://github.com/jerry-leem/notirua/releases/download/v0.3.0/Notirua-0.3.0-linux-x86_64.AppImage) (176 MB) | `chmod +x`로 실행 권한을 주고 실행 |
| Intel Mac | 준비 중 | 아래 [소스로 실행하기](#소스로-실행하기) |

- 필요 사양: RAM 8GB, 빈 디스크 약 1GB(앱, 구성요소, 중간 결과)
- macOS 앱은 아직 Apple 서명·공증 전이라 처음 열 때 경고가 나옵니다. macOS 15
  이상은 **시스템 설정 → 개인정보 보호 및 보안**에서 **그래도 열기**를, macOS 14는
  Finder에서 Control-클릭 후 **열기**를 누르세요. 한 번만 하면 됩니다.
- Windows도 아직 코드 서명 전이라 "Windows의 PC 보호" 창이 나올 수 있습니다.
  **추가 정보**를 누른 뒤 **실행**을 누르세요.
- `model-htdemucs_6s-…` 릴리스는 앱이 쓰는 악기 분리 모델의 예비 내려받기
  위치입니다. 직접 받을 필요는 없습니다.

### 릴리스를 만드는 방법 (관리자용)

1. `pyproject.toml`의 `version`을 올리고 `uv lock`을 실행합니다.
2. 플랫폼별 설치 파일을 만듭니다.
   - macOS: `uv run python packaging/build_lgpl_av.py`(처음 한 번),
     `uv run python packaging/build_app.py`, `uv run python packaging/make_dmg.py`
   - Linux: `packaging/linux/build.sh`(Docker 필요, Ubuntu 20.04 이미지 안에서 빌드)
3. `build_app.py`는 번들을 만든 뒤 `packaging/check_bundle.py`로 검사합니다. GPL
   FFmpeg, torch/tensorflow, 쓰지 않는 Qt 모듈이 들어 있거나, 번역·라이선스·모델이
   빠졌거나, 명령줄이 실행되지 않으면 실패합니다.
4. `packaging/release_notes.md`의 `{{version}}`을 바꿔 본문으로 쓰고,
   `v<버전>` 태그로 GitHub 릴리스를 만들어 설치 파일을 올립니다.
5. 서명 비밀 값(`NOTIRUA_MACOS_SIGN_IDENTITY`, `NOTIRUA_NOTARY_PROFILE`)이 있으면
   `make_dmg.py`가 서명과 공증까지 합니다.

## 소스로 실행하기

- macOS 14 Sonoma 이상(Apple Silicon, Intel), Windows 10/11(x64), Linux x86_64
- [uv](https://docs.astral.sh/uv/getting-started/installation/)와 git. Python 3.11은
  uv가 알아서 설치합니다.
- Linux만: 데스크톱 환경에는 보통 Qt 라이브러리가 이미 있습니다. 최소 설치한
  Debian/Ubuntu라면 `libegl1 libgl1 libglib2.0-0 libatomic1 libfontconfig1
  libdbus-1-3 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0
  libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0`을 설치하세요.
  한·중·일 곡명에는 CJK 글꼴(예: `fonts-noto-cjk`)이 필요합니다.

```bash
git clone https://github.com/jerry-leem/notirua.git
cd notirua
uv sync
```

## 앱 사용법

설치한 앱은 Notirua 아이콘으로 엽니다. 소스로 실행할 때는 `uv run notirua`입니다.

1. **처음 실행: 구성요소 설치.** 악기 분리 모델(246MB, MIT)과 악보 조판기
   LilyPond(39MB, GPL-3.0)가 필요합니다. 화면에 크기, 출처, 라이선스가 나옵니다.
   두 항목을 체크하고 **동의하고 설치**를 누르세요. 누르기 전에는 아무것도 내려받지
   않으며, 설치 후에는 인터넷을 쓰지 않습니다. **나중에**를 누르면 앱은 그대로
   열려 있고 위쪽에 **설치하기** 버튼이 남습니다. 인터넷이 없으면 **묶음 파일로
   설치…** 버튼을 누르세요.
2. **파일 선택.** 창 아무 곳에나 음악·동영상 파일을 끌어다 놓거나 **파일 고르기…** 버튼을
   누르세요(MP3, M4A, WAV, FLAC, OGG, AIFF, MP4 동영상 등, 15분 이하).
3. **옵션.** 곡명과 악기를 확인하고 **악보 만들기**를 누르세요. 줄 맞춤, 박자,
   빠르기, 조성, 용지, PDF 언어는 **세부 설정** 안에 있고 기본값은 자동입니다.
   같은 파일의 이전 결과가 이상하면 **세부 설정**에서 **저장된 중간 결과를 지우고
   처음부터 다시 만들기**를 체크하세요.
4. **기다리기.** 단계별 상태와 남은 시간이 보입니다. 4분 곡은 빠른 Mac에서 1분
   이내, 보통 노트북에서 몇 분 걸립니다. **취소**는 3초 안에 멈추고, 끝난 단계는
   남겨 두어 다시 시도할 때 빨라집니다.
5. **결과.** 탭으로 악기를 바꾸고 미리보기 쪽을 넘깁니다. **조 바꾸기**의 **−/+**(한
   번 누를 때마다 반음, 두 번 누르면 온음)나 조 목록으로 조를 바꿉니다. 맨 위의
   **곡명**도 여기서 바꿀 수 있고, Enter를 누르면 모든 쪽과 파일 이름에 반영됩니다
   (악보만 다시 그리므로 몇 초면 됩니다). **모두 저장**은 기존 파일을 덮어쓰지 않고
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

macOS에서는 Dock 아이콘을 오른쪽 클릭해도 **음악 파일 열기…** 메뉴와 **설정…** 메뉴가 나옵니다.
창 제목에 버전이 표시됩니다(예: `Notirua 0.3.0`).

## 명령줄 사용법

설치한 앱에서는 `uv run notirua` 대신 아래처럼 실행합니다.

- macOS: `/Applications/Notirua.app/Contents/MacOS/notirua-cli`
- Windows: `%LOCALAPPDATA%\Programs\Notirua\notirua-cli.exe` (내 계정에만 설치한 경우)
- Linux: `./Notirua-<버전>-linux-x86_64.AppImage` (인자 없이 실행하면 창이 열림)

```bash
uv run notirua setup                   # 동의를 물은 뒤 구성요소 설치
uv run notirua setup --accept-licenses # 묻지 않고 설치 (자동화용)
uv run notirua setup --bundle components.zip   # 인터넷 없이 설치

uv run notirua transcribe "곡.m4a" --out ./out
uv run notirua transcribe "곡.m4a" --out ./out --title "봄날" \
    --stems guitar,bass --transpose +2 --paper a4 --musicxml --midi
uv run notirua transcribe "공연.mp4" --start 30 --end 210 --out ./out
uv run notirua transcribe "곡.m4a" --out ./out --fresh   # 중간 결과를 지우고 처음부터

uv run notirua components              # 설치된 구성요소
uv run notirua cache                   # 저장된 중간 결과 크기
uv run notirua cache --clear
uv run notirua --lang ko               # 한국어로 창 열기
uv run notirua --lang ko transcribe --help     # 모든 옵션 (한국어)
uv run notirua --version               # notirua 0.3.0
```

## 파일이 저장되는 곳

| | macOS | Windows | Linux |
|---|---|---|---|
| 설정과 구성요소 | `~/Library/Application Support/notirua` | `%LOCALAPPDATA%\notirua` | `~/.config/notirua`, `~/.local/share/notirua` |
| 저장된 중간 결과 | `~/Library/Caches/notirua` | `%LOCALAPPDATA%\notirua\Cache` | `~/.cache/notirua` |
| 로그 (문제 신고용) | `~/Library/Logs/notirua` | `%LOCALAPPDATA%\notirua\Logs` | `~/.local/state/notirua/log` |

Notirua를 지우려면 앱(또는 소스로 내려받은 폴더)과 위 폴더들을 지우면 됩니다.

## 버전

시맨틱 버전(`MAJOR.MINOR.PATCH`)을 따릅니다. 현재 버전은 **0.3.0**이며, 1.0 전까지는
MINOR 버전에서도 동작이 바뀔 수 있습니다. `notirua --version`이나 창 제목으로 확인하고,
버전마다 바뀐 내용은 [릴리스 페이지](https://github.com/jerry-leem/notirua/releases)에
있습니다.

## 개발

```bash
uv run pytest -m "not slow"     # 빠른 오프라인 테스트 (GUI 포함)
uv run pytest -m slow           # 실제 구성요소로 하는 전체 테스트
uv run ruff check . && uv run ruff format --check . && uv run mypy src/notirua
```

## 라이선스

Notirua는 MIT 라이선스로 배포합니다(`LICENSE`). 함께 들어가거나 내려받는 구성요소는
각자의 라이선스를 따릅니다(`docs/LICENSES.md`).

## 문서

- [릴리스 페이지](https://github.com/jerry-leem/notirua/releases) — 설치 파일, 설치 방법, 바뀐 점
- `docs/LICENSES.md` — 타사 라이선스

---

## English

Turn a song into sheet music: Notirua (pronounced "no-ti-ru-a", 노티루아)
splits audio into instruments (vocals, drums, bass, guitar, piano, other),
writes each one down as notation — with
tablature for guitar and bass — lets you transpose, and saves PDFs with the
song title and page numbers. Chord symbols (such as C, Am, G7) appear above
every score wherever the chord changes. Everything runs on your computer.

### Features

#### Runs on macOS, Windows, and Linux

| System | Supported | Installer |
|---|---|---|
| macOS | 14 Sonoma or later, Apple Silicon and Intel | `.dmg` for Apple Silicon (Intel coming) |
| Windows | 10 and 11 (x64) | `.exe` setup program |
| Linux | x86_64 with glibc 2.31 or later (Ubuntu 20.04 or later, and others) | a single `.AppImage` |

The screens and features are the same everywhere; menus and shortcuts follow
each system's conventions (the application menu and ⌘ on macOS, the File menu
and Ctrl on Windows and Linux). The installers need no Python or other
programs, and the Linux one includes a font for Korean, Japanese, and Chinese
titles (macOS and Windows use their system fonts).

#### Languages

- The window, command-line help, error messages, and Qt's own dialogs are in
  **English and Korean**.
- Notirua starts in the system language. Change it in **Settings** or with
  `--lang en` / `--lang ko` (the window language applies after a restart).
- The text inside the PDF (instrument names, page numbers, and so on) can use
  a different language from the window (**More settings**, or `--pdf-lang`).
- Song titles in any language go into the PDF as written.
- Adding a language needs no code changes: add one translation file,
  `locales/<language>/LC_MESSAGES/notirua.po` (template:
  `locales/notirua.pot`). Translations are welcome.

### Download and install

The latest release is
[**Notirua 0.3.0**](https://github.com/jerry-leem/notirua/releases/tag/v0.3.0);
its page has installation and usage notes (in Korean), changes, and known
limits. Earlier versions are on [all releases](https://github.com/jerry-leem/notirua/releases).

| Computer | Download (0.3.0) | Install |
|---|---|---|
| Mac (Apple Silicon), macOS 14 or later | [Notirua-0.3.0-macos-arm64.dmg](https://github.com/jerry-leem/notirua/releases/download/v0.3.0/Notirua-0.3.0-macos-arm64.dmg) (120 MB) | Open it and drag Notirua to Applications |
| Windows 10/11 (x64) | [Notirua-0.3.0-windows-x64-setup.exe](https://github.com/jerry-leem/notirua/releases/download/v0.3.0/Notirua-0.3.0-windows-x64-setup.exe) (107 MB) | Run it and follow the steps (no administrator rights needed) |
| Linux x86_64 (glibc 2.31 or later) | [Notirua-0.3.0-linux-x86_64.AppImage](https://github.com/jerry-leem/notirua/releases/download/v0.3.0/Notirua-0.3.0-linux-x86_64.AppImage) (176 MB) | `chmod +x` it and run it |
| Intel Mac | Coming | [Run from source](#run-from-source) |

- Requirements: 8 GB RAM; about 1 GB of free disk space
- The macOS app is not signed or notarized by Apple yet, so the first launch
  shows a warning. On macOS 15 or later choose **Open Anyway** in **System
  Settings → Privacy & Security**; on macOS 14 Control-click the app in Finder
  and choose **Open**. This is needed once.
- Windows is not code-signed yet either: if "Windows protected your PC"
  appears, choose **More info**, then **Run anyway**.
- The `model-htdemucs_6s-…` release is a backup download location for the
  instrument separation model. There is no need to download it yourself.

### Making a release (maintainers)

1. Raise `version` in `pyproject.toml` and run `uv lock`.
2. Build each platform's installer.
   - macOS: `uv run python packaging/build_lgpl_av.py` (once),
     `uv run python packaging/build_app.py`, `uv run python packaging/make_dmg.py`
   - Linux: `packaging/linux/build.sh` (needs Docker; builds in Ubuntu 20.04)
3. `build_app.py` checks the bundle with `packaging/check_bundle.py`. It fails
   on GPL FFmpeg, torch/tensorflow, unused Qt modules, missing catalogs,
   notices, or model, or a command line that does not start.
4. Use `packaging/release_notes.md` (with `{{version}}` filled in) as the
   body of a GitHub release tagged `v<version>`, and attach the installers.
5. With the signing secrets (`NOTIRUA_MACOS_SIGN_IDENTITY`,
   `NOTIRUA_NOTARY_PROFILE`), `make_dmg.py` also signs and notarizes.

### Run from source

- macOS 14 Sonoma or later (Apple Silicon or Intel), Windows 10/11 (x64), or
  Linux x86_64
- 8 GB RAM; about 1 GB of disk space for the app, components, and saved results
- [uv](https://docs.astral.sh/uv/getting-started/installation/) and git. uv
  installs the right Python (3.11) by itself.
- Linux only: desktop systems usually have Qt's libraries already. On a minimal
  Debian/Ubuntu install add `libegl1 libgl1 libglib2.0-0 libatomic1
  libfontconfig1 libdbus-1-3 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4
  libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0
  libxcb-shape0`. Korean, Japanese, or Chinese titles need a CJK font such as
  `fonts-noto-cjk`.

```bash
git clone https://github.com/jerry-leem/notirua.git
cd notirua
uv sync
```

### Use the app

Open the installed app from its icon, or run `uv run notirua` from source.

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
   the PDF are under **More settings**; the defaults are automatic. If earlier
   results for the same file look wrong, check **Delete saved intermediate
   results and start over** there.
4. **Wait.** The progress screen shows each step and the time left. A
   4-minute song takes under a minute on a fast Mac and a few minutes on an
   ordinary laptop. **Cancel** stops within 3 seconds; finished steps are kept,
   so trying again is faster.
5. **Result.** Switch instruments with the tabs and page through the preview.
   Transpose with **−/+** (one semitone per press; two presses make a whole
   step) or the key list. The **Song title** at the top can still be changed;
   press Enter and every page and file name follows (only the drawing is
   redone, which takes a few seconds). **Save all** copies the PDFs to a
   folder without overwriting existing files. **MusicXML**, **MIDI**, **Save
   as WAV**, and **Hear each instrument** are at the bottom.

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
`Notirua 0.3.0`.

### Use the command line

The installed app runs the commands below without `uv run`:

- macOS: `/Applications/Notirua.app/Contents/MacOS/notirua-cli`
- Windows: `%LOCALAPPDATA%\Programs\Notirua\notirua-cli.exe` (when installed for your account only)
- Linux: `./Notirua-<version>-linux-x86_64.AppImage` (no arguments opens the window)

```bash
uv run notirua setup                   # asks before downloading the components
uv run notirua setup --accept-licenses # same, without asking (automation)
uv run notirua setup --bundle components.zip   # install without internet

uv run notirua transcribe "song.m4a" --out ./out
uv run notirua transcribe "song.m4a" --out ./out --title "Spring" \
    --stems guitar,bass --transpose +2 --paper letter --musicxml --midi
uv run notirua transcribe "live.mp4" --start 30 --end 210 --out ./out
uv run notirua transcribe "song.m4a" --out ./out --fresh  # start over without saved results

uv run notirua components              # installed components
uv run notirua cache                   # size of saved intermediate results
uv run notirua cache --clear
uv run notirua --lang en               # open the window in English
uv run notirua transcribe --help       # every option
uv run notirua --version               # notirua 0.3.0
```

More `transcribe` options: `--to-key "G major"`, `--guitar-tuning drop_d`,
`--bass-tuning five_string`, `--time-signature 3/4`, `--tempo 96`,
`--key "D minor"`, `--shift-downbeat 1`, `--tab staff|tab|both`,
`--pdf-lang ko`, `--no-combined`, `--no-separate-pdfs`, `--track N`.

### Where Notirua keeps its files

| | macOS | Windows | Linux |
|---|---|---|---|
| Settings and components | `~/Library/Application Support/notirua` | `%LOCALAPPDATA%\notirua` | `~/.config/notirua`, `~/.local/share/notirua` |
| Saved intermediate results | `~/Library/Caches/notirua` | `%LOCALAPPDATA%\notirua\Cache` | `~/.cache/notirua` |
| Logs (for bug reports) | `~/Library/Logs/notirua` | `%LOCALAPPDATA%\notirua\Logs` | `~/.local/state/notirua/log` |

To remove Notirua, delete the app (or the cloned folder) and these folders.

### Version

Notirua uses [Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`.
The current version is **0.3.0**. While the major version is 0, a minor
release may still change behavior. `notirua --version` and the window title
show it, and the [releases page](https://github.com/jerry-leem/notirua/releases)
lists what changed in each release.

### Develop

```bash
uv run pytest -m "not slow"     # fast offline tests, GUI included
uv run pytest -m slow           # end-to-end tests with the real components
uv run ruff check . && uv run ruff format --check . && uv run mypy src/notirua
```

### License

Notirua is released under the MIT License (`LICENSE`). Components it bundles or
downloads keep their own licenses (`docs/LICENSES.md`).

### Documents

- [Releases](https://github.com/jerry-leem/notirua/releases) — installers, installation notes, changes
- `docs/LICENSES.md` — third-party licenses
