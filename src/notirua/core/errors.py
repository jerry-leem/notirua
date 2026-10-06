"""Errors with fixed, untranslated codes and translatable user messages."""

from __future__ import annotations

from notirua.i18n import N_, translate_message


class NotiruaError(Exception):
    """Base error. ``code`` is stable and English-only; messages are gettext ids."""

    code = "E-UNKNOWN"
    message_id = N_("Something went wrong.")
    hint_id = N_("Try again. If the problem continues, open the log folder and report it.")

    def __init__(self, detail: str = "", **args: object) -> None:
        super().__init__(detail)
        self.detail = detail
        self.args_map: dict[str, object] = dict(args)

    def user_message(self) -> str:
        return translate_message(self.message_id, self.args_map)

    def user_hint(self) -> str:
        return translate_message(self.hint_id, self.args_map)

    def __str__(self) -> str:
        base = self.message_id.format(**self.args_map) if self.args_map else self.message_id
        return f"[{self.code}] {base}" + (f" ({self.detail})" if self.detail else "")


class Cancelled(NotiruaError):
    code = "E-CANCELLED"
    message_id = N_("The task was cancelled.")
    hint_id = N_("Start it again whenever you are ready.")


class DecodeError(NotiruaError):
    code = "E-DECODE"
    message_id = N_("The file could not be read as audio.")
    hint_id = N_("Check that the file plays in another app, or convert it to WAV or MP3.")


class CorruptFileError(DecodeError):
    code = "E-DECODE-CORRUPT"
    message_id = N_("The file appears to be damaged.")
    hint_id = N_("Try a different copy of the file.")


class NoAudioTrackError(DecodeError):
    code = "E-DECODE-NO-AUDIO"
    message_id = N_("The file has no audio track.")
    hint_id = N_("Choose a file that contains sound.")


class DrmProtectedError(DecodeError):
    code = "E-DECODE-DRM"
    message_id = N_("The file is copy-protected (DRM) and cannot be opened.")
    hint_id = N_("Use a file without copy protection.")


class TooLongError(DecodeError):
    code = "E-DECODE-TOO-LONG"
    message_id = N_("The audio is longer than {limit} minutes.")
    hint_id = N_("Choose a section of {limit} minutes or less.")


class MultipleAudioTracksError(DecodeError):
    code = "E-DECODE-MULTI-TRACK"
    message_id = N_("The file has {count} audio tracks.")
    hint_id = N_("Choose which audio track to use.")


class ComponentMissingError(NotiruaError):
    code = "E-COMPONENT-MISSING"
    message_id = N_("A required component is not installed: {name}.")
    hint_id = N_("Open setup and install the required components.")


class JobDiskSpaceError(NotiruaError):
    code = "E-DISK-FULL"
    message_id = N_("Not enough disk space: {needed} needed, {available} available.")
    hint_id = N_("Free up disk space or clear saved intermediate results in Settings.")


class EngraveError(NotiruaError):
    code = "E-ENGRAVE"
    message_id = N_("The score could not be drawn.")
    hint_id = N_("Open the log folder for details and report the problem.")


class EngraveTimeoutError(EngraveError):
    code = "E-ENGRAVE-TIMEOUT"
    message_id = N_("Drawing the score took too long and was stopped.")
    hint_id = N_("Try fewer instruments or a shorter section.")


class DownloadError(NotiruaError):
    code = "E-DOWNLOAD"
    message_id = N_("The download failed.")
    hint_id = N_("Check your internet connection and try again.")


class ChecksumMismatchError(DownloadError):
    code = "E-DOWNLOAD-CHECKSUM"
    message_id = N_("The downloaded file is damaged (checksum mismatch).")
    hint_id = N_("Try again. The damaged file has been removed.")


class DiskSpaceError(DownloadError):
    code = "E-DOWNLOAD-DISK"
    message_id = N_("Not enough disk space: {needed} needed, {available} available.")
    hint_id = N_("Free up disk space or choose another install location.")


class PermissionDeniedError(DownloadError):
    code = "E-DOWNLOAD-PERMISSION"
    message_id = N_("Cannot write to the install location.")
    hint_id = N_("Choose a folder you can write to.")


class ConsentRequiredError(NotiruaError):
    code = "E-CONSENT"
    message_id = N_("Downloading components needs your permission first.")
    hint_id = N_("Review the components and choose “Agree and install”.")
