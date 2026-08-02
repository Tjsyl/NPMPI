"""
Single combined credential file for npmpi, encrypted with Windows DPAPI.

DPAPI (CryptProtectData/CryptUnprotectData) ties the encrypted bytes to the
current Windows user + machine - nobody else, and no other machine, can
decrypt this file even if they copy it, and npmpi never has to store or ask
for a master password. Trade-off (by design, per Travis): this file only
ever works on the one Windows account/machine it was created on.

Implemented via ctypes straight against crypt32.dll so the package doesn't
need the pywin32 dependency.

Layout on disk: one JSON blob, shape:
{
  "<site key>": {
    "npm_password": "...",
    "piholes": {"<pihole name>": "...", ...}
  },
  ...
}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_CREDS_PATH = Path.home() / ".npmpi" / "credentials.dat"


class CredentialError(RuntimeError):
    pass


def _dpapi_available() -> bool:
    return sys.platform == "win32"


def _protect(data: bytes) -> bytes:
    if not _dpapi_available():
        raise CredentialError(
            "DPAPI encryption is only available on Windows. "
            "npmpi's credential store is Windows-only by design (see README)."
        )
    import ctypes
    import ctypes.wintypes as wt

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def to_blob(b: bytes) -> DATA_BLOB:
        buf = ctypes.create_string_buffer(b, len(b))
        return DATA_BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    in_blob = to_blob(data)
    out_blob = DATA_BLOB()
    desc = "npmpi credentials"
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob), desc, None, None, None, 0, ctypes.byref(out_blob)
    )
    if not ok:
        raise CredentialError("CryptProtectData failed - could not encrypt credential file")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _unprotect(data: bytes) -> bytes:
    if not _dpapi_available():
        raise CredentialError(
            "DPAPI decryption is only available on Windows."
        )
    import ctypes
    import ctypes.wintypes as wt

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def to_blob(b: bytes) -> DATA_BLOB:
        buf = ctypes.create_string_buffer(b, len(b))
        return DATA_BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    in_blob = to_blob(data)
    out_blob = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    )
    if not ok:
        raise CredentialError(
            "CryptUnprotectData failed - the credential file may belong to a "
            "different Windows user/machine, or is corrupt. Re-run `npmpi setup`."
        )
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def creds_exist(path: Path = DEFAULT_CREDS_PATH) -> bool:
    return path.exists()


def load_creds(path: Path = DEFAULT_CREDS_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"No credential file at {path}. Run `npmpi setup` first.")
    encrypted = path.read_bytes()
    plaintext = _unprotect(encrypted)
    return json.loads(plaintext.decode("utf-8"))


def save_creds(creds: dict[str, Any], path: Path = DEFAULT_CREDS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plaintext = json.dumps(creds).encode("utf-8")
    encrypted = _protect(plaintext)
    path.write_bytes(encrypted)
    try:
        path.chmod(0o600)
    except (NotImplementedError, OSError):
        pass  # best-effort; DPAPI is the real protection here


def get_npm_password(creds: dict[str, Any], site_key: str) -> str:
    try:
        return creds[site_key]["npm_password"]
    except KeyError as e:
        raise CredentialError(f"No stored NPM password for site '{site_key}'. Run `npmpi setup`.") from e


def get_pihole_password(creds: dict[str, Any], site_key: str, pihole_name: str) -> str:
    try:
        return creds[site_key]["piholes"][pihole_name]
    except KeyError as e:
        raise CredentialError(
            f"No stored password for pihole '{pihole_name}' on site '{site_key}'. Run `npmpi setup`."
        ) from e
