# Notirua {{version}}

노래 파일을 넣으면 악기별(보컬, 드럼, 베이스, 기타, 피아노, 다른 악기)로 나누어 오선보와 기타·베이스 TAB 악보를 그리고, 곡명과 페이지 번호가 들어간 PDF로 저장하는 데스크톱 앱입니다. 모든 악보 맨 위에는 코드(예: C, Am, G7)가 표시됩니다. 나눈 악기 가운데 원하는 것만 골라 새 음원 파일(MP3, M4A, WAV)로 만들 수도 있어, 보컬만 뺀 MR이나 연습용 반주를 쉽게 만듭니다. 모든 처리는 내 컴퓨터에서 이루어집니다.

## 내려받기

아래 **Assets**에서 내 컴퓨터에 맞는 파일 하나를 받으세요.

| 컴퓨터 | 받을 파일 |
|---|---|
| Mac (Apple Silicon: M1 이후), macOS 14 Sonoma 이상 | `Notirua-0.4.0-macos-arm64.dmg` (0.4.0 릴리스) |
| Windows 10/11 (x64) | `Notirua-{{version}}-windows-x64-setup.exe` |
| Linux x86_64 (Ubuntu 20.04 이상 등 glibc 2.31 이상) | `Notirua-0.4.0-linux-x86_64.AppImage` (0.4.0 릴리스) |
| Intel Mac | 준비 중입니다. 지금은 [소스로 실행](https://github.com/jerry-leem/notirua#소스로-실행하기)할 수 있습니다. |

필요 사양: RAM 8GB, 빈 디스크 약 1GB(앱, 구성요소, 중간 결과).

`model-htdemucs_6s-…` 릴리스는 앱이 쓰는 악기 분리 모델의 예비 내려받기 위치입니다.
직접 받을 필요는 없습니다.

## 설치

### macOS

1. 받은 `.dmg` 파일을 열고, **Notirua**를 옆의 **Applications** 폴더로 끌어다 놓습니다.
2. 응용 프로그램 폴더에서 Notirua를 엽니다.
3. 아직 Apple 서명과 공증을 받기 전이라 처음 열 때 경고가 나옵니다. 한 번만 아래처럼 허용하면 그다음부터는 바로 열립니다.
   - macOS 15 Sequoia 이상: 경고 창에서 **완료**를 누른 뒤 **시스템 설정 → 개인정보 보호 및 보안**으로 가서 아래쪽의 **그래도 열기**를 누르고 암호를 입력합니다.
   - macOS 14 Sonoma: Finder에서 Notirua를 Control-클릭(오른쪽 클릭)하고 **열기**를 고른 뒤, 다시 나오는 창에서 **열기**를 누릅니다.

### Windows

1. 받은 `Notirua-{{version}}-windows-x64-setup.exe`를 실행합니다.
2. 아직 코드 서명 전이라 "Windows의 PC 보호" 창이 나올 수 있습니다. **추가 정보**를 누른 뒤 **실행**을 누르세요.
3. 안내에 따라 설치합니다. 관리자 권한 없이 내 계정에만 설치되며, 시작 메뉴에 Notirua가 생깁니다. 지울 때는 **설정 → 앱**에서 Notirua를 제거합니다.

### Linux

```bash
chmod +x Notirua-0.4.0-linux-x86_64.AppImage
./Notirua-0.4.0-linux-x86_64.AppImage
```

파일 관리자에서 파일 속성의 "프로그램으로 실행 허용"을 켠 뒤 두 번 클릭해도 됩니다.
FUSE가 없어 실행되지 않으면 `--appimage-extract-and-run`을 붙여 실행하세요.
한·중·일 곡명이 들어간 PDF용 글꼴(Noto Sans CJK)은 앱 안에 들어 있습니다.

## 처음 실행: 구성요소 설치

악보를 만들려면 구성요소 두 개가 더 필요합니다. 첫 화면에 크기, 출처, 라이선스가 나옵니다.

- 악기 분리 모델(246MB, MIT)
- 악보 조판기 LilyPond(39MB, GPL-3.0)

두 항목을 체크하고 **동의하고 설치**를 누르세요. 누르기 전에는 아무것도 내려받지 않으며, 설치한 뒤에는 인터넷을 쓰지 않습니다. 인터넷이 없는 컴퓨터라면 **묶음 파일로 설치…** 버튼을 누르세요.

## 사용법

1. **파일 고르기.** 창에 음악·동영상 파일을 끌어다 놓거나 **파일 고르기…** 버튼을 누릅니다(MP3, M4A, WAV, FLAC, OGG, AIFF, MP4 동영상 등, 15분 이하).
2. **옵션.** 곡명과 악기를 확인하고 **악보 만들기**를 누릅니다. 줄 맞춤, 박자, 빠르기, 조성, 용지는 **세부 설정** 안에 있고 기본값은 자동입니다.
3. **기다리기.** 단계별 상태와 남은 시간이 보입니다. 4분 곡은 빠른 Mac에서 1분 안팎, 보통 노트북에서 몇 분 걸립니다.
4. **결과.** 탭으로 악기를 바꾸며 미리 봅니다. **조 바꾸기**의 **−/+** 버튼은 한 번에 반음씩 조를 바꿉니다. 곡명도 여기서 고칠 수 있습니다. **모두 저장**을 누르면 PDF가 폴더에 저장되고, 아래쪽 버튼으로 MusicXML, MIDI, WAV도 저장할 수 있습니다.
5. **음원 만들기.** 결과 화면 아래쪽의 **음원 만들기**를 누르면 남길 악기를 골라 새 음원 파일 하나로 저장합니다. **보컬 빼기(MR)** 버튼을 누르면 보컬만 뺀 반주가 되고, **미리 듣기**로 먼저 들어 볼 수 있습니다. 형식은 MP3(기본), M4A, WAV 가운데 고릅니다.
   악보와 같은 구간을 쓰며, 악보의 조를 바꿨어도 음원은 원래 음높이 그대로입니다.

언어, 용지, 저장 폴더는 **설정**(macOS ⌘, / Windows·Linux Ctrl+,)에서 바꿉니다.

## 명령줄로 쓰기

```bash
# macOS
/Applications/Notirua.app/Contents/MacOS/notirua-cli transcribe "곡.m4a" --out ~/Desktop/악보

# Windows (PowerShell)
& "$env:LOCALAPPDATA\Programs\Notirua\notirua-cli.exe" transcribe "곡.m4a" --out "$HOME\Desktop\악보"

# Linux
./Notirua-0.4.0-linux-x86_64.AppImage transcribe "곡.m4a" --out ./악보
```

`--transpose +2`(조 바꾸기), `--stems guitar,bass`(악기 고르기), `--start 30 --end 210`(구간), `--musicxml --midi` 같은 옵션이 있습니다. 전체 옵션은 `transcribe --help`로 봅니다(`--lang ko`를 앞에 붙이면 한국어).

고른 악기만 합친 음원은 `mix` 명령으로 만듭니다.

```bash
notirua-cli mix "곡.m4a" --out ./음원                       # 보컬만 뺀 MR (MP3)
notirua-cli mix "곡.m4a" --out ./음원 --without guitar      # 기타만 뺀 반주
notirua-cli mix "곡.m4a" --out ./음원 --stems drums,bass --format wav
```

## 이번 버전에서 바뀐 점

Windows 버그 수정판입니다.

- **옛 버전 위에 덮어 설치해도 새 버전이 표시됩니다.** 설치 프로그램이 이전 설치의 프로그램 파일을 먼저 지우도록 바꿨습니다. 설정, 구성요소, 중간 결과는 그대로 남습니다. (0.4.1을 0.4.0 위에 덮어 설치하면 창 제목이 0.4.0으로 보일 수 있었습니다.)
- 창 제목에 앱 이름이 두 번 나오던 것(`Notirua 0.4.2 - Notirua`)을 고쳤습니다.
- 0.4.1의 수정이 모두 들어 있습니다. 한국어 Windows에서 화면이 영어로 나오던 문제, 악보 만들기가 조 분석 단계에서 멈추던 문제(`'NoneType' object has no attribute 'write'`), 그래픽 가속(DirectML) 오류 메시지가 깨지던 문제입니다.

이번 버전은 **Windows 설치 파일만** 새로 나왔습니다. Mac과 Linux는 0.4.0 파일에 위 수정이 들어 있지 않습니다.

0.4.0에서 추가된 기능: **트랙을 골라 새 음원 만들기.** 악기별로 나눈 트랙(보컬, 드럼, 베이스, 기타, 피아노, 다른 악기) 가운데 원하는 것만 골라 MP3(320 kbps), M4A(AAC 256 kbps), WAV(16비트) 파일 하나로 저장합니다. 보컬만 뺀 MR, 내 악기만 뺀 합주·연습용 반주, 공연용 음원을 만들 때 씁니다. 결과 화면의 **음원 만들기** 버튼이나 명령줄 `mix`로 만듭니다. 이미 악보를 만든 곡은 악기를 다시 나누지 않아 몇 초 만에 저장됩니다.

그동안 쌓인 기능: 세 운영체제 설치 파일(0.3.0), 모든 악보 위 코드 표시(0.2.3), 저장된 중간 결과를 지우고 처음부터 다시 만들기(0.2.2), 기타·베이스 TAB에서 음을 훨씬 덜 빠뜨림(0.2.1).

## 알려진 제한

- macOS와 Windows 앱은 아직 코드 서명 전이라 처음 열 때 위의 허용 과정이 필요합니다.
- Intel Mac 설치 파일은 준비 중입니다.
- 드럼 채보는 아직 거칩니다. 박자는 항상 4/4로 추정하므로, 다른 박자의 곡은 **세부 설정**에서 박자를 직접 고르세요.
- 15분이 넘는 파일은 명령줄의 `--start`, `--end`로 구간을 나눠 처리하세요.
- 새 음원은 악기 분리 결과를 그대로 더한 것이라, 뺀 악기의 소리가 조금 남거나 남긴 악기의 소리가 조금 줄 수 있습니다. 악보의 조 바꾸기는 음원에 적용되지 않습니다.

## 지우기

앱(macOS는 응용 프로그램 폴더의 Notirua, Windows는 **설정 → 앱**에서 제거, Linux는 AppImage 파일)을 지우고, 설정·구성요소·중간 결과 폴더를 지우면 됩니다.

| | macOS | Windows | Linux |
|---|---|---|---|
| 설정과 구성요소 | `~/Library/Application Support/notirua` | `%LOCALAPPDATA%\notirua` | `~/.config/notirua`, `~/.local/share/notirua` |
| 중간 결과 | `~/Library/Caches/notirua` | `%LOCALAPPDATA%\notirua\Cache` | `~/.cache/notirua` |

문제가 있으면 [Issues](https://github.com/jerry-leem/notirua/issues)에 알려 주세요.
로그 위치는 [README](https://github.com/jerry-leem/notirua#파일이-저장되는-곳)에 있습니다.
