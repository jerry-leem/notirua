"""The macOS menu bar name when Notirua runs from source (no PyObjC needed).

macOS titles the application menu with the main bundle's ``CFBundleName``.
A plain Python interpreter has none, so the menu says "python3". Setting the
key in the (mutable) info dictionary before QApplication starts fixes that.
Packaged builds carry the name in their Info.plist instead.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from collections.abc import Callable
from typing import Any

Send = Callable[..., Any]


def _runtime() -> tuple[Send, Callable[[str], Any], Any] | None:
    """(message sender, NSString maker, main bundle info dictionary), or None."""
    if sys.platform != "darwin":
        return None
    try:
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc") or "libobjc.dylib")
        ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Foundation.framework/Foundation")
    except OSError:
        return None
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    raw_send = objc.objc_msgSend

    def send(target: Any, selector: bytes, *args: Any, restype: Any = ctypes.c_void_p) -> Any:
        # objc_msgSend must be called with the exact prototype (arm64 ABI).
        raw_send.restype = restype
        raw_send.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + [
            ctypes.c_char_p if isinstance(a, bytes) else ctypes.c_void_p for a in args
        ]
        target = objc.objc_getClass(target) if isinstance(target, bytes) else target
        return raw_send(target, objc.sel_registerName(selector), *args)

    def nsstring(text: str) -> Any:
        return send(b"NSString", b"stringWithUTF8String:", text.encode())

    info = send(send(b"NSBundle", b"mainBundle"), b"infoDictionary")
    if not info:
        return None
    setter = objc.sel_registerName(b"setObject:forKey:")
    if not send(info, b"respondsToSelector:", setter, restype=ctypes.c_bool):
        return None
    return send, nsstring, info


def set_app_name(name: str) -> bool:
    """Call before QApplication is created. Returns False off macOS or on failure."""
    runtime = _runtime()
    if runtime is None:
        return False
    send, nsstring, info = runtime
    send(info, b"setObject:forKey:", nsstring(name), nsstring("CFBundleName"))
    return app_name() == name


def app_name() -> str | None:
    runtime = _runtime()
    if runtime is None:
        return None
    send, nsstring, info = runtime
    value = send(info, b"objectForKey:", nsstring("CFBundleName"))
    if not value:
        return None
    raw = send(value, b"UTF8String", restype=ctypes.c_char_p)
    return raw.decode() if isinstance(raw, bytes) else None
