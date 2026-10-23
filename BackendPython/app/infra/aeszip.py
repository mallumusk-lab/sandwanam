"""Password-protected ZIP files (WinZip AES-256, opened by 7-Zip, WinZip and macOS tools).

`encrypt_zip` makes the emailed backup ZIP; `read_backup_zip` opens one again for Import
backup, in memory. The password is only used to decrypt: it is never stored or logged.

pyzipper is imported lazily, so the API still starts (with email reported as not set up)
when the package is missing.
"""
from __future__ import annotations

import io
import re
import zlib
from datetime import datetime
from typing import Iterable

from ..errors import Invalid, ServiceUnavailable

_BACKUP_ENTRY = re.compile(r"backup_[^/\\]*\.json")  # top level only, like the emailed ZIP


def available() -> bool:
    try:
        import pyzipper  # noqa: F401
    except ImportError:
        return False
    return True


def _safe_name(name: str) -> str:
    if not name or name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/") or ":" in name:
        raise ValueError("ZIP entry names must be plain relative file names.")
    return name


def encrypt_zip(entries: Iterable[tuple[str, bytes]], password: str, *, modified: datetime) -> bytes:
    """A ZIP with every entry deflated and encrypted with AES-256 under `password`."""
    import pyzipper

    if not password:
        raise ValueError("A ZIP password is required.")
    stamp = modified.timetuple()[:6]
    if stamp[0] < 1980:
        raise ValueError("ZIP timestamps start in 1980.")
    buffer = io.BytesIO()
    with pyzipper.AESZipFile(buffer, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as archive:
        archive.setpassword(password.encode("utf-8"))
        archive.setencryption(pyzipper.WZ_AES, nbits=256)
        for name, data in entries:
            info = archive.zipinfo_cls(_safe_name(name), date_time=stamp)
            info.compress_type = pyzipper.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, data)
    return buffer.getvalue()


def _too_large(limit: int) -> Invalid:
    return Invalid(f"The backup is larger than {limit // (1024 * 1024)} MB.", code="invalid_backup")


def read_backup_zip(data: bytes, password: str, *, limit: int) -> bytes:
    """The bytes of the single `backup_*.json` inside an emailed backup ZIP.

    The ZIP itself and the unpacked entry must each stay within `limit` bytes; the entry is
    read with that cap, so a ZIP that lies about its sizes cannot use more memory. Raises
    Invalid (`zip_password` for a wrong password, `invalid_backup` otherwise).
    """
    try:
        import pyzipper
    except ImportError:
        raise ServiceUnavailable("This server cannot open ZIP files yet. Upload the .json file from inside the ZIP "
                                 "instead.", code="zip_unavailable") from None
    data = bytes(data)
    if len(data) > limit:
        raise _too_large(limit)
    damaged = Invalid("The file is not a backup ZIP, or it is damaged.", code="invalid_backup")
    try:
        archive = pyzipper.AESZipFile(io.BytesIO(data))
    except (pyzipper.BadZipFile, ValueError, OSError, EOFError):
        raise damaged from None
    with archive:
        entries = [info for info in archive.infolist() if _BACKUP_ENTRY.fullmatch(info.filename)]
        if len(entries) != 1:
            raise Invalid("The ZIP must hold exactly one backup_….json file, like the emailed backup.",
                          code="invalid_backup")
        (entry,) = entries
        if entry.file_size > limit:
            raise _too_large(limit)
        archive.setpassword(password.encode("utf-8"))
        try:
            with archive.open(entry) as stream:
                raw = stream.read(limit + 1)
        except (pyzipper.BadZipFile, NotImplementedError, ValueError, OSError, EOFError, zlib.error):
            raise damaged from None  # listed first: NotImplementedError is a RuntimeError
        except RuntimeError:  # pyzipper: "Bad password for file …"
            raise Invalid("The ZIP password is wrong.", code="zip_password",
                          details={"field": "zip_password"}) from None
    if len(raw) > limit:
        raise _too_large(limit)
    return raw
