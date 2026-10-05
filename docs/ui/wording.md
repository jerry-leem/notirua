# Screen wording rules / 화면 문구 규칙

Notirua talks to people who have never heard of source separation. Screen
text (GUI, CLI messages, errors, PDF labels) must not use the terms below.
`tests/test_i18n.py::test_ui_wording_avoids_jargon` checks every message in
`locales/notirua.pot` against this list. Product and format names that users
see on files (MIDI, MusicXML, LilyPond) are allowed.

Notirua 사용자는 음원 분리 같은 용어를 모릅니다. 화면 문구에는 아래 단어를
쓰지 않습니다. 파일 형식과 제품 이름(MIDI, MusicXML, LilyPond)은 허용합니다.

## Banned terms / 금지어

- `stem`
- `stems`
- `ONNX`
- `quantize`
- `quantization`
- `transcription`
- `inference`
- `onset`
- `Demucs`
- `htdemucs`
- `Basic Pitch`
- `Viterbi`
- `runtime`
- `PCM`
- `codec`
- `sample rate`
- `beat tracking`

## Preferred phrasing / 권장 표현

| Avoid | Say instead | 한국어 |
|---|---|---|
| separating stems | Splitting the song into instruments | 악기별로 나누는 중 |
| quantizing | Fitting notes to the beat | 박자에 맞춰 정리하는 중 |
| transcribing | Listening for notes | 음을 듣고 받아 적는 중 |
| engraving | Drawing the sheet music | 악보를 그리는 중 |
| stem is silent | No sound | 소리 없음 |
