# Notirua (노티루아)

Notirua(노티루아)는 음원 파일을 넣으면 악기별(보컬, 드럼, 베이스, 기타, 피아노, 다른 악기)로
나누고, 악보와 기타·베이스 TAB 악보를 만들어 곡명과 페이지 번호가 들어간 PDF로
저장하는 데스크톱 앱입니다. 모든 악보 맨 위에는 코드(예: C, Am, G7)가 코드가 바뀌는
곳에만 표시됩니다. 나눈 악기 가운데 원하는 것만 골라 합친 새 음원(예: 보컬만 뺀 MR)도
만들 수 있습니다. 음원 파일 대신 유튜브 영상 링크를 붙여넣어도 됩니다. 모든 처리는 내
컴퓨터에서 이루어집니다.

[English instructions are below.](#english)

## 주요 특징

### 음원을 악보 PDF로 만들기

Notirua의 핵심 기능입니다. 노래 파일(MP3, M4A, WAV, FLAC 등 오디오와 MP4 같은
동영상)을 넣으면 곡명과 페이지 번호가 들어간 악보 PDF를 만들어 줍니다.

1. **악기별로 나누기**: 보컬, 드럼, 베이스, 기타, 피아노, 다른 악기로 나눕니다.
2. **악보로 옮기기**: 악기마다 오선보를 그리고, 기타와 베이스는 TAB 악보도 함께
   그립니다. 맨 위에는 코드(예: C, Am, G7)가 코드가 바뀌는 곳에만 표시됩니다.
3. **PDF로 저장**: 곡명과 페이지 번호가 들어간 PDF로 저장합니다. 결과 화면에서 조를
   바꾸거나 곡명을 고친 뒤 다시 저장할 수 있고, MusicXML과 MIDI도 함께 저장할 수
   있습니다.

모든 처리는 내 컴퓨터에서 이루어지며, 처음 한 번 구성요소를 설치한 뒤에는 인터넷을
쓰지 않습니다(유튜브 링크를 쓸 때만 예외입니다). 사용 방법은 [앱 사용법](#앱-사용법)을
보세요.

### 유튜브 링크로 음원 받기

음원 파일이 없어도 됩니다. 첫 화면에 유튜브 영상 링크를 붙여넣으면 소리만 MP3 파일로
저장하고, 이어서 악보 PDF까지 한 번에 만들 수 있습니다.

1. 영상의 링크를 복사합니다(브라우저 주소창 또는 **공유** 버튼).
2. Notirua 첫 화면에서 **붙여넣기**를 누르거나 Ctrl+V(macOS는 ⌘V)를 누릅니다. 클립보드에
   유튜브 링크가 있으면 화면이 알려 줍니다. 링크가 영상 하나의 주소가 맞는지 바로 검사하고,
   재생목록이나 채널 주소처럼 맞지 않으면 이유를 알려 줍니다.
3. **음질**을 고릅니다. 기본은 160 kbps이고 128, 192, 256, 320 kbps도 고를 수 있습니다.
4. **음원 저장 후 악보 만들기**를 누릅니다. 소리를 내려받아 영상 제목을 파일 이름으로 한
   MP3로 저장한 뒤(기본 위치는 음악 폴더 안의 `Notirua`, 설정에서 바꿀 수 있습니다) 곧바로
   악보 만들기로 이어집니다. 음원만 받으려면 **음원을 저장한 뒤 바로 악보 만들기**를 끄세요.
   그러면 저장한 뒤 옵션 화면에서 멈추고, 다시 누르면 악보를 만듭니다.

처음 쓸 때 도우미 프로그램(Deno, 약 41MB, MIT)을 한 번 내려받습니다. 동의를 먼저 묻고,
동의하기 전에는 아무것도 내려받지 않습니다. 유튜브 링크를 쓸 때만 인터넷을 사용하며, 소리를
받은 뒤의 모든 처리는 내 컴퓨터에서 이루어집니다.

유의할 점:

- 사용할 권리가 있는 영상만 쓰세요. 유튜브 이용약관과 저작권법이 적용됩니다.
- 15분 이하의 공개 영상만 받을 수 있습니다. 실시간 방송, 비공개·멤버십·연령 제한 영상은
  받지 못합니다.
- 유튜브가 바뀌면 링크가 갑자기 안 될 수 있습니다. 그럴 때는 새 버전의 Notirua를
  설치하세요.

### 트랙을 골라 새 음원 만들기

악기별로 나눈 트랙(보컬, 드럼, 베이스, 기타, 피아노, 다른 악기) 가운데 원하는 것만
골라 새 음원 파일(MP3, M4A, WAV)로 만들 수 있습니다. 보컬만 뺀 MR, 내 악기만 뺀
합주·연습용 반주, 공연용 음원을 만들 때 씁니다. 결과 화면의 **음원 만들기** 버튼이나
명령줄 `notirua mix`로 만듭니다.

- **보컬 빼기(MR)**, **모두 선택**, **모두 해제** 버튼으로 빠르게 고르고, **미리 듣기**로
  먼저 들어 볼 수 있습니다.
- MP3는 320 kbps, M4A는 AAC 256 kbps, WAV는 16비트로 저장합니다(44.1 kHz 스테레오).
- 악보를 만든 구간과 같은 구간을 쓰고, 악보의 조를 바꿔도 음원은 원래 음높이
  그대로입니다. 이미 악기를 나눈 곡은 다시 나누지 않아 몇 초면 끝납니다.
- 파일 이름이 담긴 악기를 알려 줍니다(예: `곡 - MR.mp3`, `곡 - 기타 제외.mp3`,
  `곡 - 드럼, 베이스.mp3`).

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

최신 배포판은 [**Notirua 0.5.0 릴리스 페이지**](https://github.com/jerry-leem/notirua/releases/tag/v0.5.0)에
있습니다. 릴리스 페이지에 한국어 설치 방법, 사용법, 바뀐 점, 알려진 제한이 함께 적혀
있습니다. 지난 버전은 [모든 릴리스](https://github.com/jerry-leem/notirua/releases)에서
볼 수 있습니다.

| 컴퓨터 | 내려받기 | 설치 |
|---|---|---|
| Windows 10/11 (x64) | [Notirua-0.5.0-windows-x64-setup.exe](https://github.com/jerry-leem/notirua/releases/download/v0.5.0/Notirua-0.5.0-windows-x64-setup.exe) | 실행해서 안내에 따라 설치(관리자 권한 필요 없음) |
| Mac (Apple Silicon), macOS 14 이상 | [Notirua-0.5.0-macos-arm64.dmg](https://github.com/jerry-leem/notirua/releases/download/v0.5.0/Notirua-0.5.0-macos-arm64.dmg) | 열어서 Notirua를 Applications 폴더로 끌어다 놓기 |
| Linux x86_64 (glibc 2.31 이상) | [Notirua-0.5.0-linux-x86_64.AppImage](https://github.com/jerry-leem/notirua/releases/download/v0.5.0/Notirua-0.5.0-linux-x86_64.AppImage) | `chmod +x`로 실행 권한을 주고 실행 |
| Intel Mac | 준비 중 | 아래 [소스로 실행하기](#소스로-실행하기) |

macOS 14에서는 악보를 그리는 조판기(LilyPond)가 시작되지 않을 수 있습니다. 확인된 환경은 macOS 15 이상입니다.

- 필요 사양: RAM 8GB, 빈 디스크 약 1GB(앱, 구성요소, 중간 결과)
- macOS 앱은 아직 Apple 서명·공증 전이라 처음 열 때 경고가 나옵니다. macOS 15
  이상은 **시스템 설정 → 개인정보 보호 및 보안**에서 **그래도 열기**를, macOS 14는
  Finder에서 Control-클릭 후 **열기**를 누르세요. 한 번만 하면 됩니다.
- Windows도 아직 코드 서명 전이라 "Windows의 PC 보호" 창이 나올 수 있습니다.
  **추가 정보**를 누른 뒤 **실행**을 누르세요.
- `model-htdemucs_6s-…` 릴리스는 앱이 쓰는 악기 분리 모델의 예비 내려받기
  위치입니다. 직접 받을 필요는 없습니다.

### 릴리스를 만드는 방법 (관리자용)

1. `uv run python scripts/bump_version.py <새 버전>`을 실행합니다. `pyproject.toml`,
   `uv.lock`, README의 "현재 버전" 문장을 한 번에 바꾸며, 앱 창 제목·`--version`·설치 파일
   이름은 빌드할 때 `pyproject.toml`에서 읽습니다. 버전이 어긋나면 `tests/test_versions.py`와
   릴리스 빌드(태그 확인, 번들 메타데이터 검사)가 실패합니다. 다운로드 표의 릴리스 링크는
   직접 고칩니다.
2. 플랫폼별 설치 파일을 만듭니다.
   - macOS: `uv run python packaging/build_lgpl_av.py`(처음 한 번, FFmpeg 설정이 바뀌면 다시),
     `uv run python packaging/build_app.py`, `uv run python packaging/make_dmg.py`
   - Linux: `packaging/linux/build.sh`(Docker 필요, Ubuntu 20.04 이미지 안에서 빌드)
   - Windows: `gh workflow run release.yml --ref main`(GitHub Actions), 끝나면
     `gh run download <run-id> -n notirua-windows -D dist/windows`
3. `build_app.py`는 번들을 만든 뒤 `packaging/check_bundle.py`로 검사합니다. GPL
   FFmpeg, torch/tensorflow, 쓰지 않는 Qt 모듈이 들어 있거나, 번역·라이선스·모델이
   빠졌거나, 명령줄이 실행되지 않으면 실패합니다.
4. `uv run python packaging/versioning.py --notes`가 `{{version}}`을 채운 본문을 출력합니다.
   이를 본문으로 쓰고,
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
   않으며, 설치 후에는 인터넷을 쓰지 않습니다(유튜브 링크를 쓸 때만 예외). **나중에**를 누르면 앱은 그대로
   열려 있고 위쪽에 **설치하기** 버튼이 남습니다. 인터넷이 없으면 **묶음 파일로
   설치…** 버튼을 누르세요.
2. **파일 선택.** 창 아무 곳에나 음악·동영상 파일을 끌어다 놓거나 **파일 고르기…** 버튼을
   누르세요(MP3, M4A, WAV, FLAC, OGG, AIFF, MP4 동영상 등, 15분 이하). 파일 대신 클립보드에
   복사한 **유튜브 링크**를 **붙여넣기**(또는 Ctrl+V, macOS는 ⌘V)로 넣을 수도 있습니다.
   링크는 검사한 뒤 소리만 MP3로 저장하고, 기본값으로는 곧바로 악보까지 만듭니다
   ([유튜브 링크로 음원 받기](#유튜브-링크로-음원-받기)).
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
   **악기별 소리 듣기**, **음원 만들기**가 있습니다.
6. **음원 만들기.** 남길 악기를 체크하고(기본은 보컬만 뺀 MR) 형식을 고른 뒤
   **저장…** 버튼을 누릅니다. 소리가 없는 악기는 흐리게 보이며 고를 수 없습니다.

**설정**에서 언어, 용지, 저장 폴더를 바꾸고 구성요소를 관리하며 중간 결과를 비울
수 있습니다. 오른쪽 위 버튼이나 메뉴로 엽니다.

| | macOS | Windows / Linux |
|---|---|---|
| 설정 | **Notirua → 설정…** (⌘,) | **파일 → 설정…** (Ctrl+,) |
| 종료 | **Notirua → Notirua 종료** (⌘Q) | **파일 → Notirua 종료** (Ctrl+Q) |
| 정보와 라이선스 | **Notirua → Notirua 정보** | **도움말 → Notirua 정보** |
| 파일 열기 / 모두 저장 | **파일** 메뉴 (⌘O / ⌘S) | **파일** 메뉴 (Ctrl+O / Ctrl+S) |

macOS에서는 Dock 아이콘을 오른쪽 클릭해도 **음악 파일 열기…** 메뉴와 **설정…** 메뉴가 나옵니다.
창 제목에 버전이 표시됩니다(예: `Notirua 0.5.0`).

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

uv run notirua mix "곡.m4a" --out ./out                  # 보컬만 뺀 MR (MP3)
uv run notirua mix "곡.m4a" --out ./out --without guitar # 기타만 뺀 반주
uv run notirua mix "곡.m4a" --out ./out --stems drums,bass --format wav

uv run notirua youtube "https://youtu.be/영상ID" --out ./음원             # 소리만 MP3로 (기본 160 kbps)
uv run notirua youtube "https://youtu.be/영상ID" --bitrate 320          # 128, 160, 192, 256, 320
uv run notirua transcribe "https://youtu.be/영상ID" --out ./out         # 받은 뒤 바로 악보까지
uv run notirua setup --youtube         # 유튜브용 도우미 프로그램(Deno) 설치
uv run notirua youtube --check         # 유튜브 기능이 설치되어 있는지 확인 (인터넷 불필요)

uv run notirua components              # 설치된 구성요소
uv run notirua cache                   # 저장된 중간 결과 크기
uv run notirua cache --clear
uv run notirua --lang ko               # 한국어로 창 열기
uv run notirua --lang ko transcribe --help     # 모든 옵션 (한국어)
uv run notirua --version               # notirua 0.5.0
```

## 파일이 저장되는 곳

| | macOS | Windows | Linux |
|---|---|---|---|
| 설정과 구성요소 | `~/Library/Application Support/notirua` | `%LOCALAPPDATA%\notirua` | `~/.config/notirua`, `~/.local/share/notirua` |
| 저장된 중간 결과 | `~/Library/Caches/notirua` | `%LOCALAPPDATA%\notirua\Cache` | `~/.cache/notirua` |
| 로그 (문제 신고용) | `~/Library/Logs/notirua` | `%LOCALAPPDATA%\notirua\Logs` | `~/.local/state/notirua/log` |

Notirua를 지우려면 앱(또는 소스로 내려받은 폴더)과 위 폴더들을 지우면 됩니다.

## 버전

시맨틱 버전(`MAJOR.MINOR.PATCH`)을 따릅니다. 현재 버전은 **0.5.0**이며, 1.0 전까지는
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
every score wherever the chord changes. You can also save a new audio file
with only the instruments you choose, such as a backing track without
vocals. You can also paste a YouTube video link instead of a file. Everything
runs on your computer.

### Features

#### Turn a song into sheet music (PDF)

This is Notirua's main feature. Add a song (audio such as MP3, M4A, WAV, or
FLAC, or a video such as MP4) and get sheet music as a PDF with the song title
and page numbers.

1. **Split into instruments**: vocals, drums, bass, guitar, piano, and other.
2. **Write it down**: each instrument gets a staff score, and guitar and bass
   also get tablature. Chord symbols (such as C, Am, G7) appear above the
   score wherever the chord changes.
3. **Save as PDF**: the PDF carries the song title and page numbers. On the
   result screen you can change the key or fix the title and save again, and
   you can also save MusicXML and MIDI.

Everything runs on your computer, and after the one-time component setup it
does not use the internet (YouTube links are the one exception). See
[Use the app](#use-the-app).

#### Save audio from a YouTube link

You do not need an audio file. Paste a YouTube video link on the first screen
and Notirua saves the sound as an MP3 file, then goes on to the sheet music PDF
in one go.

1. Copy the video's link (the browser's address bar or the **Share** button).
2. On Notirua's first screen press **Paste**, or press Ctrl+V (⌘V on macOS). The
   screen tells you when the clipboard holds a YouTube link. The link is checked
   at once: playlists, channels, and other addresses are refused with a reason.
3. Choose the **Quality**. The default is 160 kbps; 128, 192, 256, and 320 kbps
   are also offered.
4. Press **Save audio and make sheet music**. Notirua downloads the sound and
   saves an MP3 named after the video (by default in `Notirua` inside your Music
   folder; change it in Settings), then carries on to the sheet music. To get
   only the audio, turn off **Make the sheet music right after saving the
   audio**: Notirua then stops at the options screen after saving.

The first time, a small helper program (Deno, about 41 MB, MIT) is downloaded
once. Notirua asks first and downloads nothing before you agree. The internet is
used only for YouTube links; everything after the sound is downloaded happens on
your computer.

Please note:

- Only use videos you have the right to use. YouTube's terms of service and
  copyright law apply.
- Public videos of 15 minutes or less only. Live streams and private,
  members-only, or age-restricted videos cannot be saved.
- When YouTube changes, links may suddenly stop working. Install the newest
  Notirua when that happens.

#### Make a new audio file from chosen tracks

Pick any of the separated tracks (vocals, drums, bass, guitar, piano, other)
and save just those as a new audio file (MP3, M4A, or WAV) — a backing track
without vocals, a practice mix without your own instrument, or a mix for a
live show. Use **Make audio file** on the result screen or `notirua mix` on
the command line.

- Choose quickly with **Remove vocals (MR)**, **Select all**, and **Clear
  all**, and use **Listen first** before saving.
- MP3 is 320 kbps, M4A is AAC at 256 kbps, and WAV is 16-bit (44.1 kHz
  stereo).
- The audio uses the same time range as the sheet music and keeps its
  original key, even after you transpose. A song that is already split takes
  only seconds.
- File names say what the mix holds, for example `Song - backing track.mp3`,
  `Song - without Guitar.mp3`, or `Song - Drums, Bass.mp3`.

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
[**Notirua 0.5.0**](https://github.com/jerry-leem/notirua/releases/tag/v0.5.0);
its page has installation and usage notes (in Korean), changes, and known
limits. Earlier versions are on [all releases](https://github.com/jerry-leem/notirua/releases).

| Computer | Download | Install |
|---|---|---|
| Windows 10/11 (x64) | [Notirua-0.5.0-windows-x64-setup.exe](https://github.com/jerry-leem/notirua/releases/download/v0.5.0/Notirua-0.5.0-windows-x64-setup.exe) | Run it and follow the steps (no administrator rights needed) |
| Mac (Apple Silicon), macOS 14 or later | [Notirua-0.5.0-macos-arm64.dmg](https://github.com/jerry-leem/notirua/releases/download/v0.5.0/Notirua-0.5.0-macos-arm64.dmg) | Open it and drag Notirua to Applications |
| Linux x86_64 (glibc 2.31 or later) | [Notirua-0.5.0-linux-x86_64.AppImage](https://github.com/jerry-leem/notirua/releases/download/v0.5.0/Notirua-0.5.0-linux-x86_64.AppImage) | `chmod +x` it and run it |
| Intel Mac | Coming | [Run from source](#run-from-source) |

On macOS 14 the sheet-music engraver (LilyPond) may not start. macOS 15 or later is the tested setup.

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

1. Run `uv run python scripts/bump_version.py <new version>`. It changes `pyproject.toml`,
   `uv.lock`, and the README's "current version" sentences in one go; the window title,
   `--version`, and installer file names read `pyproject.toml` when built. If a copy drifts,
   `tests/test_versions.py` and the release build (tag check, bundle metadata check) fail.
   Release links in the download table are edited by hand.
2. Build each platform's installer.
   - macOS: `uv run python packaging/build_lgpl_av.py` (once, and again when the FFmpeg setup changes),
     `uv run python packaging/build_app.py`, `uv run python packaging/make_dmg.py`
   - Linux: `packaging/linux/build.sh` (needs Docker; builds in Ubuntu 20.04)
   - Windows: `gh workflow run release.yml --ref main` (GitHub Actions), then
     `gh run download <run-id> -n notirua-windows -D dist/windows`
3. `build_app.py` checks the bundle with `packaging/check_bundle.py`. It fails
   on GPL FFmpeg, torch/tensorflow, unused Qt modules, missing catalogs,
   notices, or model, or a command line that does not start.
4. Use the output of `uv run python packaging/versioning.py --notes` (the notes with `{{version}}` filled in) as the
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
   that, and the internet is not used afterwards (except for YouTube links). **Not now** keeps the app
   open with an **Install** button at the top. Without internet, use
   **Install from a bundle file…**.
2. **Choose a file.** Drop a music or video file anywhere in the window, or
   use **Choose a file…** (MP3, M4A, WAV, FLAC, OGG, AIFF, MP4 video, and
   more, up to 15 minutes). Instead of a file you can paste a **YouTube link**
   from the clipboard with **Paste** (or Ctrl+V, ⌘V on macOS). The link is
   checked, the sound is saved as an MP3, and by default the sheet music
   follows at once ([Save audio from a YouTube link](#save-audio-from-a-youtube-link)).
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
   as WAV**, **Hear each instrument**, and **Make audio file** are at the
   bottom.
6. **Make audio file.** Check the instruments to keep (everything but the
   vocals at first), choose a file type, and choose **Save…**. Instruments
   with no sound are dimmed and cannot be chosen.

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
`Notirua 0.5.0`.

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

uv run notirua mix "song.m4a" --out ./out                  # backing track without vocals (MP3)
uv run notirua mix "song.m4a" --out ./out --without guitar # everything but the guitar
uv run notirua mix "song.m4a" --out ./out --stems drums,bass --format wav

uv run notirua youtube "https://youtu.be/VIDEO_ID" --out ./audio     # sound only, as MP3 (160 kbps)
uv run notirua youtube "https://youtu.be/VIDEO_ID" --bitrate 320      # 128, 160, 192, 256, 320
uv run notirua transcribe "https://youtu.be/VIDEO_ID" --out ./out     # save, then sheet music
uv run notirua setup --youtube         # install the helper program for YouTube links (Deno)
uv run notirua youtube --check         # is YouTube support installed? (no internet needed)

uv run notirua components              # installed components
uv run notirua cache                   # size of saved intermediate results
uv run notirua cache --clear
uv run notirua --lang en               # open the window in English
uv run notirua transcribe --help       # every option
uv run notirua --version               # notirua 0.5.0
```

More `transcribe` options: `--to-key "G major"`, `--guitar-tuning drop_d`,
`--bass-tuning five_string`, `--time-signature 3/4`, `--tempo 96`,
`--key "D minor"`, `--shift-downbeat 1`, `--tab staff|tab|both`,
`--pdf-lang ko`, `--no-combined`, `--no-separate-pdfs`, `--track N`.
`mix` takes `--stems` or `--without` (comma separated), `--format mp3|m4a|wav`,
`--title`, `--track`, `--start`, and `--end`; with neither `--stems` nor
`--without` it leaves out the vocals.

### Where Notirua keeps its files

| | macOS | Windows | Linux |
|---|---|---|---|
| Settings and components | `~/Library/Application Support/notirua` | `%LOCALAPPDATA%\notirua` | `~/.config/notirua`, `~/.local/share/notirua` |
| Saved intermediate results | `~/Library/Caches/notirua` | `%LOCALAPPDATA%\notirua\Cache` | `~/.cache/notirua` |
| Logs (for bug reports) | `~/Library/Logs/notirua` | `%LOCALAPPDATA%\notirua\Logs` | `~/.local/state/notirua/log` |

To remove Notirua, delete the app (or the cloned folder) and these folders.

### Version

Notirua uses [Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`.
The current version is **0.5.0**. While the major version is 0, a minor
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
