"""ONNX Runtime session creation with accelerator selection and silent CPU fallback (FR-2)."""

from __future__ import annotations

import locale
import logging
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

CPU = "CPUExecutionProvider"


def describe_error(exc: BaseException) -> str:
    """Readable text for an onnxruntime failure.

    Driver and DirectML messages come in the OS code page (cp949 on Korean
    Windows), but onnxruntime hands them to Python as UTF-8, so Python raises
    UnicodeDecodeError. The error still carries the raw bytes: decode them with
    the OS encoding instead.
    """
    if isinstance(exc, UnicodeDecodeError) and isinstance(exc.object, bytes | bytearray):
        encodings = ["mbcs"] if sys.platform == "win32" else []
        encodings.append(locale.getpreferredencoding(False))
        for encoding in encodings:
            try:
                return bytes(exc.object).decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue
        return bytes(exc.object).decode("utf-8", errors="replace")
    return str(exc)


def preferred_providers() -> list[str]:
    """CoreML on macOS, DirectML on Windows, CPU elsewhere; CPU always last."""
    import onnxruntime as ort

    available = set(ort.get_available_providers())
    wanted: list[str] = []
    if sys.platform == "darwin" and "CoreMLExecutionProvider" in available:
        wanted.append("CoreMLExecutionProvider")
    elif sys.platform == "win32" and "DmlExecutionProvider" in available:
        wanted.append("DmlExecutionProvider")
    wanted.append(CPU)
    return wanted


def make_session(
    model_path: Path, accelerate: bool = True, threads: int = 0, low_memory: bool = False
) -> Any:
    """Create an ``InferenceSession``; if the accelerator fails, log it and use the CPU.

    ``low_memory`` disables the CPU memory arena; for htdemucs_6s this lowers
    peak RSS by ~550 MB at no measurable speed cost (M0-S2).
    """
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.log_severity_level = 3
    if low_memory:
        opts.enable_cpu_mem_arena = False
        opts.enable_mem_pattern = False
    if threads:
        opts.intra_op_num_threads = threads
    providers = preferred_providers() if accelerate else [CPU]
    if providers != [CPU]:
        try:
            session = ort.InferenceSession(str(model_path), sess_options=opts, providers=providers)
            log.info("onnx session %s using %s", model_path.name, session.get_providers())
            return session
        except Exception as exc:  # accelerator init failures vary by driver
            log.warning(
                "accelerator %s failed for %s, falling back to CPU: %s",
                providers[0],
                model_path.name,
                describe_error(exc),
            )
    session = ort.InferenceSession(str(model_path), sess_options=opts, providers=[CPU])
    log.info("onnx session %s using CPU", model_path.name)
    return session


def run_with_fallback(
    session: Any, model_path: Path, outputs: list[str], feeds: dict[str, Any]
) -> tuple[Any, list[Any]]:
    """Run once; if an accelerated session fails at run time, rebuild on CPU and retry.

    Returns ``(session, results)`` so callers keep the working session.
    """
    try:
        return session, session.run(outputs, feeds)
    except Exception as exc:
        if session.get_providers()[0] == CPU:
            raise
        log.warning(
            "accelerated run failed, switching %s to CPU: %s", model_path.name, describe_error(exc)
        )
        cpu = make_session(model_path, accelerate=False, low_memory=True)
        return cpu, cpu.run(outputs, feeds)
