"""Generate the en_XA pseudo-locale to find hard-coded and truncated strings (SPEC 6.7).

Usage: uv run python scripts/make_pseudo_locale.py
Writes locales/en_XA/LC_MESSAGES/notirua.po (git-ignored). Run the app with
--lang en_XA: every translated string is accented and ~40% longer, so English
text that is still plain was not wrapped in _() and clipped text shows layout bugs.
"""

from __future__ import annotations

import re
from pathlib import Path

from babel.messages.catalog import Catalog
from babel.messages.pofile import read_po, write_po

ACCENTS = str.maketrans(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "àƀçđéƒĝĥîĵķļɱñöþǫŕšţûṽŵẋýžÀßÇÐÉƑĜĤÎĴĶĻṀÑÖÞǪŔŠŢÛṼŴẊÝŽ",
)
PLACEHOLDER = re.compile(r"(\{\w+\})")


def pseudo(text: str) -> str:
    parts = PLACEHOLDER.split(text)
    out = "".join(p if PLACEHOLDER.fullmatch(p) else p.translate(ACCENTS) for p in parts)
    padding = "~" * max(1, round(len(text) * 0.4))
    return f"[{out}{padding}]"


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "locales"
    with (root / "notirua.pot").open("rb") as fp:
        template = read_po(fp)
    catalog = Catalog(locale="en", project="Notirua")
    for message in template:
        if not message.id:
            continue
        if isinstance(message.id, tuple):
            catalog.add(message.id, tuple(pseudo(i) for i in message.id))
        else:
            catalog.add(message.id, pseudo(message.id))
    target = root / "en_XA" / "LC_MESSAGES" / "notirua.po"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as fp:
        write_po(fp, catalog)
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
