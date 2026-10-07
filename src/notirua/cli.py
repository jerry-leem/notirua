"""Command-line interface. Mirrors the GUI features by calling :mod:`notirua.core.pipeline`."""

from __future__ import annotations

import argparse
import io
import math
import shutil
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from notirua import __version__
from notirua import settings as settings_mod
from notirua.core import youtube as yt
from notirua.core.errors import Cancelled, InvalidYoutubeLinkError, NotiruaError
from notirua.core.model import STEMS
from notirua.core.progress import CancelToken, ProgressEvent
from notirua.i18n import (
    _,
    available_languages,
    ngettext,
    resolve_language,
    set_language,
    translate_progress,
)
from notirua.i18n.argparse_text import install as install_argparse_text

EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_CANCELLED, EXIT_SETUP = 0, 1, 2, 130, 3

STATE_LABELS = {
    "pending": "·",
    "running": "▶",
    "done": "✓",
    "skipped": "–",
    "failed": "✗",
}


def _format_eta(seconds: float | None) -> str:
    if seconds is None:
        return ""
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


class ProgressPrinter:
    """A redrawn progress bar on terminals; plain line logs otherwise (FR-11)."""

    def __init__(self, stream: TextIO = sys.stderr) -> None:
        self.stream = stream
        self.tty = stream.isatty()
        self._last_line = ""
        self._last_stage_state: tuple[str, str] | None = None
        self._last_logged = -1.0

    def __call__(self, event: ProgressEvent) -> None:
        message = translate_progress(event.message_id, event.message_args)
        pct = int(event.overall_fraction * 100)
        if self.tty:
            width = max(10, min(30, shutil.get_terminal_size((80, 20)).columns - 50))
            filled = int(width * event.overall_fraction)
            bar = "█" * filled + "░" * (width - filled)
            eta = _format_eta(event.eta_seconds)
            eta_text = " " + _("about {time} left").format(time=eta) if eta else ""
            line = f"\r{bar} {pct:3d}% {message}{eta_text}"
            pad = max(0, len(self._last_line) - len(line))
            self.stream.write(line + " " * pad)
            self._last_line = line
            if event.stage_state in ("done", "failed", "skipped"):
                self.stream.write(
                    f"\r{STATE_LABELS[event.stage_state]} {message}"
                    + " " * max(0, len(line) - len(message))
                    + "\n"
                )
                self._last_line = ""
            self.stream.flush()
            return
        key = (event.stage, event.stage_state)
        if key != self._last_stage_state or pct - self._last_logged >= 10:
            self.stream.write(f"[{pct:3d}%] {STATE_LABELS[event.stage_state]} {message}\n")
            self.stream.flush()
            self._last_stage_state = key
            self._last_logged = pct


def _print_error(exc: NotiruaError) -> None:
    print(_("Error: {message}").format(message=exc.user_message()), file=sys.stderr)
    print(_("What to do: {hint}").format(hint=exc.user_hint()), file=sys.stderr)
    print(_("Error code: {code}").format(code=exc.code), file=sys.stderr)


def _whole_number(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            _("{value} is not a whole number.").format(value=repr(text))
        ) from None


def _number(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError(_("{value} is not a number.").format(value=repr(text)))
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="notirua",
        description=_("Turn a song into sheet music and tablature PDFs."),
    )
    parser.add_argument(
        "--version", action="version", version=f"notirua {__version__}", help=_("Show the version.")
    )
    parser.add_argument("--lang", help=_("Interface language, for example en or ko."))
    parser.add_argument("-v", "--verbose", action="store_true", help=_("Show detailed log output."))
    sub = parser.add_subparsers(dest="command", metavar=_("command"))

    t = sub.add_parser("transcribe", help=_("Make sheet music from an audio file."))
    t.add_argument("file", help=_("Audio or video file to read, or a YouTube video link."))
    t.add_argument("--out", type=Path, default=Path("."), help=_("Folder for the results."))
    t.add_argument("--title", help=_("Song title printed on every page."))
    t.add_argument(
        "--bitrate",
        type=_whole_number,
        choices=list(yt.BITRATES),
        help=_("For a YouTube link: MP3 quality in kbps (default {kbps}).").format(
            kbps=yt.DEFAULT_BITRATE
        ),
    )
    t.add_argument(
        "--proxy",
        help=_("For a YouTube link: proxy server, for example http://proxy.example.com:8080."),
    )
    t.add_argument(
        "--audio-out",
        type=Path,
        help=_("For a YouTube link: folder for the saved MP3 (default: Music/Notirua)."),
    )
    t.add_argument(
        "--stems",
        help=_("Instruments to include, comma separated: {choices}.").format(
            choices=",".join(STEMS)
        ),
    )
    t.add_argument(
        "--transpose", type=_whole_number, default=0, help=_("Semitones to move, -12 to +12.")
    )
    t.add_argument("--to-key", help=_('Transpose to this key, for example "G major".'))
    t.add_argument("--paper", choices=["a4", "letter"], help=_("Paper size."))
    t.add_argument("--pdf-lang", help=_("Language for labels inside the PDF."))
    t.add_argument(
        "--guitar-tuning", default=None, help=_("standard, drop_d, half_down, or MIDI numbers.")
    )
    t.add_argument(
        "--bass-tuning",
        default=None,
        help=_("standard, five_string, drop_d, half_down, or MIDI numbers."),
    )
    t.add_argument("--time-signature", help=_("For example 4/4 or 3/4."))
    t.add_argument("--tempo", type=_number, help=_("Beats per minute, if detection is wrong."))
    t.add_argument("--key", help=_('Key, if detection is wrong, for example "D minor".'))
    t.add_argument(
        "--shift-downbeat", type=_whole_number, default=0, help=_("Move the first beat by N beats.")
    )
    t.add_argument(
        "--tab",
        choices=["both", "tab", "staff"],
        default="both",
        help=_("Show notation, tablature, or both."),
    )
    t.add_argument(
        "--no-combined", action="store_true", help=_("Do not make the all-instruments PDF.")
    )
    t.add_argument(
        "--no-separate-pdfs", action="store_true", help=_("Do not make one PDF per instrument.")
    )
    t.add_argument("--musicxml", action="store_true", help=_("Also save MusicXML."))
    t.add_argument("--midi", action="store_true", help=_("Also save MIDI."))
    t.add_argument(
        "--track", type=_whole_number, help=_("Audio track number when the file has several.")
    )
    t.add_argument("--start", type=_number, help=_("Start time in seconds."))
    t.add_argument("--end", type=_number, help=_("End time in seconds."))
    t.add_argument(
        "--fresh",
        action="store_true",
        help=_("Delete this file's saved intermediate results and start over."),
    )

    m = sub.add_parser(
        "mix",
        help=_("Make an audio file from only the instruments you choose."),
        description=_(
            "Make an audio file from only the instruments you choose. "
            "Without --stems or --without, everything but the vocals is kept."
        ),
    )
    m.add_argument("file", type=Path, help=_("Audio or video file to read."))
    m.add_argument("--out", type=Path, default=Path("."), help=_("Folder for the results."))
    picks = m.add_mutually_exclusive_group()
    picks.add_argument(
        "--stems",
        help=_("Instruments to keep, comma separated: {choices}.").format(choices=",".join(STEMS)),
    )
    picks.add_argument(
        "--without",
        help=_("Instruments to leave out, comma separated: {choices}.").format(
            choices=",".join(STEMS)
        ),
    )
    m.add_argument(
        "--format",
        choices=["mp3", "m4a", "wav"],
        default="mp3",
        help=_("File type of the new audio file."),
    )
    m.add_argument("--title", help=_("Song title used in the file name."))
    m.add_argument(
        "--track", type=_whole_number, help=_("Audio track number when the file has several.")
    )
    m.add_argument("--start", type=_number, help=_("Start time in seconds."))
    m.add_argument("--end", type=_number, help=_("End time in seconds."))

    y = sub.add_parser(
        "youtube",
        help=_("Save the audio of a YouTube video as an MP3 file."),
        description=_(
            "Save the audio of a YouTube video as an MP3 file named after the video. "
            "Only use videos you have the right to use."
        ),
    )
    y.add_argument("link", nargs="?", help=_("Link of one YouTube video."))
    y.add_argument(
        "--check",
        action="store_true",
        help=_("Check offline that YouTube support is installed correctly."),
    )
    y.add_argument("--out", type=Path, help=_("Folder for the MP3 file (default: Music/Notirua)."))
    y.add_argument(
        "--bitrate",
        type=_whole_number,
        choices=list(yt.BITRATES),
        help=_("MP3 quality in kbps (default {kbps}).").format(kbps=yt.DEFAULT_BITRATE),
    )
    y.add_argument(
        "--proxy",
        help=_("Proxy server, for example http://proxy.example.com:8080 (default: the system's)."),
    )

    s = sub.add_parser("setup", help=_("Install the components Notirua needs."))
    s.add_argument(
        "--accept-licenses",
        action="store_true",
        help=_("Agree to the component licenses without asking."),
    )
    s.add_argument(
        "--bundle", type=Path, help=_("Install from a component bundle file (no internet).")
    )
    s.add_argument("--dir", type=Path, help=_("Install location."))
    s.add_argument("--remove", metavar="ID", help=_("Remove an installed component."))
    s.add_argument(
        "--youtube",
        action="store_true",
        help=_("Install the helper program that reads YouTube links (Deno)."),
    )

    sub.add_parser("components", help=_("Show installed components."))
    c = sub.add_parser("cache", help=_("Show or clear saved intermediate results."))
    c.add_argument("--clear", action="store_true", help=_("Delete all saved intermediate results."))
    sub.add_parser("languages", help=_("List available languages."))
    sub.add_parser("gui", help=_("Open the Notirua window (the default with no command)."))
    return parser


def _preparse_lang(argv: Sequence[str]) -> str | None:
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--lang="):
            return arg.split("=", 1)[1]
    return None


def _tolerate_unencodable_output() -> None:
    """Redirected output uses the system code page on Windows (often cp1252), which
    cannot hold Korean or most song titles: replace such characters, never crash."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and not stream.isatty():
            stream.reconfigure(errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    _tolerate_unencodable_output()
    user = settings_mod.load()
    set_language(resolve_language(_preparse_lang(argv) or user.language))
    install_argparse_text()
    parser = build_parser()
    args = parser.parse_args(argv)
    from notirua.core.logging_setup import configure

    configure(verbose=args.verbose)
    if args.command in ("gui", None):
        # Plain `notirua` opens the window; it starts on setup until that is done.
        from notirua.gui.app import display_available
        from notirua.gui.app import main as gui_main

        if not display_available():
            if args.command is None:
                parser.print_help()
            print(_("No screen found, so the window cannot open."), file=sys.stderr)
            return EXIT_USAGE
        return gui_main([sys.argv[0]], language=args.lang)
    try:
        if args.command == "transcribe":
            return cmd_transcribe(args, user)
        if args.command == "mix":
            return cmd_mix(args, user)
        if args.command == "youtube":
            return cmd_youtube(args, user)
        if args.command == "setup":
            return cmd_setup(args, user)
        if args.command == "components":
            return cmd_components(user)
        if args.command == "cache":
            return cmd_cache(args, user)
        if args.command == "languages":
            for lang in available_languages():
                print(lang)
            return EXIT_OK
    except Cancelled:
        print("\n" + _("Cancelled."), file=sys.stderr)
        return EXIT_CANCELLED
    except NotiruaError as exc:
        print(file=sys.stderr)
        _print_error(exc)
        return EXIT_ERROR
    return EXIT_USAGE


def _youtube_runtime(user: settings_mod.Settings) -> Path | None:
    """The Deno that reads YouTube's player scripts: the installed helper, or one on the PATH."""
    from notirua.components.manager import optional_manager_from_settings
    from notirua.components.manifest import JS_RUNTIME
    from notirua.core.errors import ComponentMissingError

    try:
        entry: Path | None = optional_manager_from_settings(user).require(JS_RUNTIME.id)
    except ComponentMissingError:
        entry = None
    return yt.find_js_runtime(entry)


def _save_youtube_audio(
    link: yt.YoutubeLink,
    out_dir: Path,
    kbps: int,
    user: settings_mod.Settings,
    proxy: str | None = None,
) -> yt.SavedAudio | int:
    """Save the MP3, or return the exit code to stop with."""
    try:
        yt.check_proxy(proxy)
    except ValueError:
        print(_("This is not a proxy address. It looks like http://proxy.example.com:8080."),
              file=sys.stderr)  # fmt: skip
        return EXIT_USAGE
    runtime = _youtube_runtime(user)
    if runtime is None:
        print(_("Reading YouTube links needs a small helper program."), file=sys.stderr)
        print(_("Run “notirua setup --youtube” first."), file=sys.stderr)
        return EXIT_SETUP
    cancel = CancelToken()
    try:
        saved = yt.save_as_mp3(
            link,
            out_dir,
            kbps,
            client=yt.YoutubeClient(runtime, proxy=proxy or user.proxy),
            progress=ProgressPrinter(),
            cancel=cancel,
        )
    except KeyboardInterrupt:
        cancel.cancel()
        raise Cancelled() from None
    print(_("Saved: {path}").format(path=saved.path))
    return saved


def _parse_youtube_link(text: str) -> yt.YoutubeLink | None:
    try:
        return yt.parse_link(text)
    except InvalidYoutubeLinkError as exc:
        print(_("Error: {message}").format(message=exc.user_message()), file=sys.stderr)
        print(_("What to do: {hint}").format(hint=exc.user_hint()), file=sys.stderr)
        return None


def _check_youtube_install(user: settings_mod.Settings) -> int:
    checks = yt.installation_check(_youtube_runtime(user))
    for check in checks:
        optional = check.name == "deno"
        mark = "✓" if check.ok else ("–" if optional else "✗")
        print(f"{mark} {check.name}: {check.detail}")
    return EXIT_OK if all(c.ok for c in checks if c.name != "deno") else EXIT_ERROR


def cmd_youtube(args: argparse.Namespace, user: settings_mod.Settings) -> int:
    if args.check:
        return _check_youtube_install(user)
    if not args.link:
        print(_("Give the link of a YouTube video."), file=sys.stderr)
        return EXIT_USAGE
    link = _parse_youtube_link(args.link)
    if link is None:
        return EXIT_USAGE
    out_dir = args.out or yt.default_folder(user.youtube_dir)
    saved = _save_youtube_audio(
        link, out_dir, args.bitrate or user.youtube_bitrate, user, args.proxy
    )
    return saved if isinstance(saved, int) else EXIT_OK


def _use_youtube_source(args: argparse.Namespace, user: settings_mod.Settings) -> int | None:
    """When ``transcribe`` got a YouTube link instead of a file: save the MP3 and use it.

    Returns an exit code to stop with, or ``None`` to go on with ``args.file``.
    """
    if Path(args.file).exists():
        return None
    try:
        link = yt.parse_link(args.file)
    except InvalidYoutubeLinkError:
        return None  # not a link either: the usual "File not found" follows
    out_dir = args.audio_out or yt.default_folder(user.youtube_dir)
    saved = _save_youtube_audio(
        link, out_dir, args.bitrate or user.youtube_bitrate, user, getattr(args, "proxy", None)
    )
    if isinstance(saved, int):
        return saved
    args.file = saved.path
    args.title = args.title or saved.title
    return None


def cmd_transcribe(args: argparse.Namespace, user: settings_mod.Settings) -> int:
    from notirua.components.manager import manager_from_settings
    from notirua.core.pipeline import INSTRUMENT_NAMES, JobOptions, Pipeline

    manager = manager_from_settings(user)
    missing = manager.missing()
    if missing:
        names = ", ".join(_(c.name_id) for c in missing)
        print(
            _("Some components are not installed yet: {names}").format(names=names), file=sys.stderr
        )
        print(_("Run “notirua setup” first."), file=sys.stderr)
        return EXIT_SETUP
    code = _use_youtube_source(args, user)
    if code is not None:
        return code
    args.file = Path(args.file)
    if not args.file.is_file():
        print(_("File not found: {path}").format(path=args.file), file=sys.stderr)
        return EXIT_USAGE
    stems = [s.strip() for s in args.stems.split(",")] if args.stems else None
    if stems:
        unknown = [s for s in stems if s not in STEMS]
        if unknown:
            print(_("Unknown instrument: {name}").format(name=", ".join(unknown)), file=sys.stderr)
            return EXIT_USAGE
    if not -12 <= args.transpose <= 12:
        print(_("Transpose must be between -12 and +12."), file=sys.stderr)
        return EXIT_USAGE
    ts = None
    if args.time_signature:
        num, _sep, den = args.time_signature.partition("/")
        ts = (int(num), int(den or 4))
    options = JobOptions(
        title=args.title,
        stems=stems,
        transpose=args.transpose,
        target_key=args.to_key,
        paper=args.paper or user.paper or settings_mod.default_paper(),
        guitar_tuning=args.guitar_tuning or user.guitar_tuning,
        bass_tuning=args.bass_tuning or user.bass_tuning,
        time_signature=ts,
        tempo_bpm=args.tempo,
        key=args.key,
        downbeat_shift=args.shift_downbeat,
        tab_mode=args.tab,
        per_stem_pdfs=not args.no_separate_pdfs,
        combined_pdf=not args.no_combined,
        export_musicxml=args.musicxml,
        export_midi=args.midi,
        pdf_language=args.pdf_lang or user.pdf_language,
        stream_index=args.track,
        start_s=args.start,
        end_s=args.end,
        tab_weights=user.tab_weights,
        fresh=args.fresh,
    )
    cancel = CancelToken()
    pipeline = Pipeline(
        stage_weights=user.stage_weights, cache_limit_bytes=int(user.cache_limit_gb * 1024**3)
    )
    try:
        result = pipeline.run(
            args.file, args.out, options, progress=ProgressPrinter(), cancel=cancel
        )
    except KeyboardInterrupt:
        cancel.cancel()
        raise Cancelled() from None
    files = [
        *result.pdfs.values(),
        *([result.combined_pdf] if result.combined_pdf else []),
        *result.other_files,
    ]
    print(
        _("Done in {seconds} s: {count}.").format(
            seconds=round(result.elapsed_s),
            count=ngettext("{n} file", "{n} files", len(files)).format(n=len(files)),
        )
    )
    for f in files:
        print(f"  {f}")
    for stem, reason in result.skipped.items():
        print(
            _("Skipped {instrument}: {reason}").format(
                instrument=_(INSTRUMENT_NAMES[stem]), reason=_(reason)
            )
        )
    for w in result.warnings:
        print(_("Note: {message}").format(message=_(w)))
    if "drums" in result.pdfs:
        print(_("Drum sheet music is for reference only."))
    return EXIT_OK


def _stem_list(text: str) -> list[str] | None:
    """Instruments named in ``text``; prints an error and returns None if one is unknown."""
    names = [s.strip() for s in text.split(",") if s.strip()]
    unknown = [s for s in names if s not in STEMS]
    if unknown:
        print(_("Unknown instrument: {name}").format(name=", ".join(unknown)), file=sys.stderr)
        return None
    if not names:
        print(_("Choose at least one instrument."), file=sys.stderr)
        return None
    return names


def cmd_mix(args: argparse.Namespace, user: settings_mod.Settings) -> int:
    from notirua.components.manager import manager_from_settings
    from notirua.core import mix
    from notirua.core.pipeline import INSTRUMENT_NAMES, JobOptions, Pipeline, safe_filename

    manager = manager_from_settings(user)
    missing = [c for c in manager.missing() if c.id == "htdemucs_6s"]
    if missing:
        names = ", ".join(_(c.name_id) for c in missing)
        print(
            _("Some components are not installed yet: {names}").format(names=names), file=sys.stderr
        )
        print(_("Run “notirua setup” first."), file=sys.stderr)
        return EXIT_SETUP
    if not args.file.is_file():
        print(_("File not found: {path}").format(path=args.file), file=sys.stderr)
        return EXIT_USAGE
    if args.stems is not None:
        chosen = _stem_list(args.stems)
        if chosen is None:
            return EXIT_USAGE
        include = set(chosen)
    else:
        left_out = _stem_list(args.without) if args.without is not None else ["vocals"]
        if left_out is None:
            return EXIT_USAGE
        include = set(STEMS) - set(left_out)
        if not include:
            print(_("Choose at least one instrument."), file=sys.stderr)
            return EXIT_USAGE
    if args.format not in mix.available_formats():
        print(
            _("This copy of Notirua cannot save {format} files.").format(
                format=args.format.upper()
            ),
            file=sys.stderr,
        )
        return EXIT_USAGE
    options = JobOptions(
        title=args.title, stream_index=args.track, start_s=args.start, end_s=args.end
    )
    suffix = mix.FORMATS[args.format][0]

    def target(title: str, silent: list[str]) -> Path:
        available = [s for s in STEMS if s not in silent]
        name = mix.mix_name(title, include, available, _, INSTRUMENT_NAMES)
        return Path(args.out) / f"{safe_filename(name)}{suffix}"

    cancel = CancelToken()
    pipeline = Pipeline(
        stage_weights=user.stage_weights, cache_limit_bytes=int(user.cache_limit_gb * 1024**3)
    )
    try:
        result = pipeline.export_mix(
            args.file,
            include,
            target,
            args.format,
            options,
            progress=ProgressPrinter(),
            cancel=cancel,
        )
    except KeyboardInterrupt:
        cancel.cancel()
        raise Cancelled() from None
    print(
        _("Done in {seconds} s: {count}.").format(
            seconds=round(result.elapsed_s),
            count=ngettext("{n} file", "{n} files", 1).format(n=1),
        )
    )
    print(f"  {result.path}")
    quiet = [s for s in result.silent if s in include]
    if quiet:
        names = mix.join_names([_(INSTRUMENT_NAMES[s]) for s in quiet], _)
        print(_("No sound in this song: {instruments}").format(instruments=names))
    return EXIT_OK


def cmd_setup(args: argparse.Namespace, user: settings_mod.Settings) -> int:
    from notirua.components.manager import ComponentManager, human_size, manager_from_settings
    from notirua.components.manifest import by_id

    if args.dir:
        user.components_dir = str(args.dir.expanduser().resolve())
    if args.youtube:
        return _setup_youtube_helper(args, user)
    manager = ComponentManager(user.components_path) if args.dir else manager_from_settings(user)
    printer = ProgressPrinter()
    if args.remove:
        manager.remove(by_id(args.remove))
        print(_("Removed {name}.").format(name=args.remove))
        return EXIT_OK
    if args.bundle:
        installed = manager.install_from_bundle(args.bundle, progress=printer)
        user.consent = manager.make_consent(installed)
        settings_mod.save(user)
        print(_("Installed from the bundle file."))
        return EXIT_OK
    todo = manager.missing(required_only=False)
    if not todo:
        # Installed earlier (e.g. from a bundle); record the versions in use.
        if not manager.consent_is_current(user.consent, manager.components):
            user.consent = manager.make_consent(manager.components)
            settings_mod.save(user)
        print(_("All components are installed."))
        return EXIT_OK
    plan = manager.plan(todo)
    print(_("Notirua needs to download these components:"))
    for c in todo:
        f = c.file_for(manager.platform_key)
        print(f"\n  • {_(c.name_id)} {c.version}")
        print(f"    {_(c.purpose_id)}")
        print("    " + _("Size: {size}").format(size=human_size(f.size if f else 0)))
        print("    " + _("Source: {domain}").format(domain=f.domain if f else "-"))
        print(
            "    " + _("License: {license} ({url})").format(license=c.license_id, url=c.license_url)
        )
    print()
    print(_("Total download: {size}").format(size=human_size(plan.download_bytes)))
    print(_("Disk space needed: {size}").format(size=human_size(plan.install_bytes)))
    print(_("Free space: {size}").format(size=human_size(plan.free_bytes)))
    print(_("Install location: {path}").format(path=plan.install_dir))
    print(_("The internet is used only for this download. Notirua works offline afterwards."))
    if not plan.enough_space:
        print(_("There is not enough disk space."), file=sys.stderr)
        return EXIT_ERROR
    if not args.accept_licenses:
        if not sys.stdin.isatty():
            print(_("Run again with --accept-licenses to agree without a prompt."), file=sys.stderr)
            return EXIT_USAGE
        answer = input(_("Agree to the licenses and install? [y/N] ")).strip().lower()
        if answer not in ("y", "yes", _("y"), _("yes")):
            print(_("Nothing was downloaded. Run “notirua setup” again any time."))
            return EXIT_SETUP
    consent = manager.make_consent(todo)
    user.consent = consent
    settings_mod.save(user)
    started = time.monotonic()
    try:
        manager.install(todo, consent, progress=printer)
    except KeyboardInterrupt:
        raise Cancelled() from None
    print(
        _("Components installed in {seconds} s.").format(seconds=round(time.monotonic() - started))
    )
    return EXIT_OK


def _setup_youtube_helper(args: argparse.Namespace, user: settings_mod.Settings) -> int:
    """Install Deno (optional): same consent rules as the other components."""
    from notirua.components.manager import human_size, optional_manager_from_settings
    from notirua.components.manifest import JS_RUNTIME

    manager = optional_manager_from_settings(user)
    if not manager.missing(required_only=False):
        print(_("The helper program for YouTube links is installed."))
        return EXIT_OK
    plan = manager.plan([JS_RUNTIME])
    f = JS_RUNTIME.file_for(manager.platform_key)
    print(_("Reading YouTube links needs a small helper program:"))
    print(f"\n  • {_(JS_RUNTIME.name_id)} {JS_RUNTIME.version}")
    print(f"    {_(JS_RUNTIME.purpose_id)}")
    print("    " + _("Size: {size}").format(size=human_size(f.size if f else 0)))
    print("    " + _("Source: {domain}").format(domain=f.domain if f else "-"))
    print(
        "    "
        + _("License: {license} ({url})").format(
            license=JS_RUNTIME.license_id, url=JS_RUNTIME.license_url
        )
    )
    print()
    print(_("Disk space needed: {size}").format(size=human_size(plan.install_bytes)))
    print(_("Install location: {path}").format(path=plan.install_dir))
    if not plan.enough_space:
        print(_("There is not enough disk space."), file=sys.stderr)
        return EXIT_ERROR
    if not args.accept_licenses:
        if not sys.stdin.isatty():
            print(_("Run again with --accept-licenses to agree without a prompt."), file=sys.stderr)
            return EXIT_USAGE
        answer = input(_("Agree to the license and install? [y/N] ")).strip().lower()
        if answer not in ("y", "yes", _("y"), _("yes")):
            print(_("Nothing was downloaded."))
            return EXIT_SETUP
    try:
        manager.install(
            [JS_RUNTIME], manager.make_consent([JS_RUNTIME]), progress=ProgressPrinter()
        )
    except KeyboardInterrupt:
        raise Cancelled() from None
    print(_("The helper program is installed."))
    return EXIT_OK


def cmd_components(user: settings_mod.Settings) -> int:
    from notirua.components.manager import (
        human_size,
        manager_from_settings,
        optional_manager_from_settings,
    )

    statuses = [
        *manager_from_settings(user).status(),
        *optional_manager_from_settings(user).status(),
    ]
    for st in statuses:
        state = _("installed") if st.installed else _("not installed")
        size = human_size(st.size_on_disk) if st.installed else "-"
        print(f"{st.component.id:14s} {st.component.version:28s} {state:14s} {size}")
    return EXIT_OK


def cmd_cache(args: argparse.Namespace, user: settings_mod.Settings) -> int:
    from notirua import paths
    from notirua.components.manager import human_size
    from notirua.core import cache

    root = paths.cache_dir() / "jobs"
    if args.clear:
        freed = cache.clear(root)
        print(_("Freed {size}.").format(size=human_size(freed)))
    else:
        print(
            _("Saved intermediate results: {size} in {path}").format(
                size=human_size(cache.cache_size(root)), path=root
            )
        )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
