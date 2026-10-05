# Notirua

Turn a song into sheet music: Notirua splits audio into instruments (vocals,
drums, bass, guitar, piano, other), writes each one down as notation — with
tablature for guitar and bass — lets you transpose, and saves PDFs with the
song title and page numbers. Everything runs locally.

> Status: early development (see `PROGRESS.md`). The command-line pipeline
> works; the desktop GUI and installers are not built yet.

## Try the command line (developers)

```bash
uv sync
uv run notirua setup              # asks before downloading ~285 MB of components
uv run notirua transcribe "song.m4a" --out ./out --transpose +2
uv run notirua --lang ko --help   # 한국어
```

## 한국어

Notirua는 음원 파일을 넣으면 악기별(보컬, 드럼, 베이스, 기타, 피아노, 기타 소리)로
나누고, 악보와 기타·베이스 TAB 악보를 만들어 곡명과 페이지 번호가 들어간 PDF로
저장하는 데스크톱 앱입니다. 모든 처리는 내 컴퓨터에서 이루어집니다.

> 현재 개발 초기 단계입니다(`PROGRESS.md` 참고). 명령줄 파이프라인은 동작하며,
> GUI와 설치 파일은 아직 없습니다.

## Documents

- `SPEC.md` — requirements (Korean) · `AGENTS.md` — contributor/agent guide
- `PROGRESS.md` — current status and next steps
- `docs/DECISIONS.md` — measurements and decisions · `docs/LICENSES.md` — third-party licenses
- `docs/TRANSLATING.md` — how to add a language
