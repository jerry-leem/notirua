"""Translate argparse's built-in text ("usage:", "options", error messages).

argparse looks up its strings with module-level ``_`` and ``ngettext`` bound to the
stdlib ``gettext`` default domain, which never sees Notirua's catalogs. Rebinding
them to :mod:`notirua.i18n` makes ``--help`` and usage errors follow ``--lang``.
The messages below are copied verbatim from argparse (Python 3.11) so extraction
puts them in ``notirua.pot``; a test fails if argparse gains a message not listed
here. Developer-only errors (bad ``add_argument`` calls) stay untranslated.
"""

from __future__ import annotations

import argparse

from notirua.i18n import N_, _, ngettext

MESSAGES = (
    N_("usage: "),
    N_("%(heading)s:"),
    N_("positional arguments"),
    N_("options"),
    N_("show this help message and exit"),
    N_("show program's version number and exit"),
    N_(" (default: %(default)s)"),
    N_("%(prog)s: error: %(message)s\n"),
    N_("argument %(argument_name)s: %(message)s"),
    N_("ambiguous option: %(option)s could match %(matches)s"),
    N_("expected one argument"),
    N_("expected at most one argument"),
    N_("expected at least one argument"),
    N_("ignored explicit argument %r"),
    N_("invalid %(type)s value: %(value)r"),
    N_("invalid choice: %(value)r (choose from %(choices)s)"),
    N_("not allowed with argument %s"),
    N_("one of the arguments %s is required"),
    N_("the following arguments are required: %s"),
    N_("unexpected option string: %s"),
    N_("unknown parser %(parser_name)r (choices: %(choices)s)"),
    N_("unrecognized arguments: %s"),
    N_('argument "-" with mode %r'),
    N_("can't open '%(filename)s': %(error)s"),
)


def _plural_messages() -> None:  # pragma: no cover - marks plural ids for extraction only
    ngettext("expected %s argument", "expected %s arguments", 1)


def install() -> None:
    """Route argparse's message lookups through the active Notirua catalog."""
    argparse._ = _  # type: ignore[attr-defined]
    argparse.ngettext = ngettext  # type: ignore[attr-defined]
