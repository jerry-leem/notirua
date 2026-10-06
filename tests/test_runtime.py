"""ONNX runtime helpers."""

from __future__ import annotations

import pytest


def test_describe_error_decodes_os_code_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """onnxruntime passes cp949 driver messages as UTF-8; read them with the OS encoding."""
    from notirua.core import runtime

    monkeypatch.setattr(runtime.sys, "platform", "linux")
    monkeypatch.setattr(runtime.locale, "getpreferredencoding", lambda _=False: "cp949")
    raw = "장치 오류".encode("cp949")
    with pytest.raises(UnicodeDecodeError) as info:
        raw.decode("utf-8")
    assert runtime.describe_error(info.value) == "장치 오류"
    assert runtime.describe_error(ValueError("plain")) == "plain"
