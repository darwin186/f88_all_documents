"""Excel-safe signed snapshots used by round-trip workbooks.

OOXML reserves strings shaped like ``_xFFFF_`` for escaped Unicode codepoints.
A normal Django signing token can contain that sequence by chance, after which
Excel changes the token when the workbook is opened and saved. Hex encoding
keeps new tokens outside that namespace. The legacy recovery path lets files
already affected by Excel continue to import.
"""
import base64
import hashlib
import json
from itertools import product

from django.core import signing


BASE64_PREFIX = "v3."
HEX_PREFIX = "v2."
MAX_LEGACY_CANDIDATES = 256


def dumps(value, *, salt):
    signed = signing.dumps(value, salt=salt, compress=True)
    return BASE64_PREFIX + base64.b64encode(signed.encode("ascii")).decode("ascii")


def digest(value):
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    # The digest is inside a cryptographically signed token. A 128-bit prefix
    # is ample for change detection and keeps one token compact per Excel row.
    checksum = hashlib.sha256(serialized).digest()[:16]
    return base64.urlsafe_b64encode(checksum).decode("ascii").rstrip("=")


def _case_variants(codepoint):
    hexadecimal = f"{codepoint:04x}"
    choices = [(char.lower(), char.upper()) if char.isalpha() else (char,) for char in hexadecimal]
    return ["_x" + "".join(chars) + "_" for chars in product(*choices)]


def _legacy_candidates(value):
    candidates = [""]
    for char in value:
        replacements = [char] if ord(char) < 128 else _case_variants(ord(char))
        candidates = [prefix + replacement for prefix in candidates for replacement in replacements]
        if len(candidates) > MAX_LEGACY_CANDIDATES:
            return []
    return candidates


def loads(value, *, salt):
    token = str(value or "")
    if token.startswith(BASE64_PREFIX):
        try:
            token = base64.b64decode(token[len(BASE64_PREFIX):], validate=True).decode("ascii")
        except (ValueError, UnicodeDecodeError) as exc:
            raise signing.BadSignature("Token bảo vệ trong file Excel không hợp lệ.") from exc
        return signing.loads(token, salt=salt)
    if token.startswith(HEX_PREFIX):
        try:
            token = bytes.fromhex(token[len(HEX_PREFIX):]).decode("ascii")
        except (ValueError, UnicodeDecodeError) as exc:
            raise signing.BadSignature("Token bảo vệ trong file Excel không hợp lệ.") from exc
        return signing.loads(token, salt=salt)

    try:
        return signing.loads(token, salt=salt)
    except signing.BadSignature as original_error:
        # Excel decodes a coincidental `_xFFFF_` substring into one Unicode
        # character. Signed tokens are ASCII, so every non-ASCII character is
        # safe to treat as a possible OOXML escape and verify cryptographically.
        for candidate in _legacy_candidates(token):
            if candidate == token:
                continue
            try:
                return signing.loads(candidate, salt=salt)
            except signing.BadSignature:
                pass
        raise original_error
