"""Rest.li 2.0 URL encoding, as the app's DataEncoder writes GraphQL variables."""

import re
from collections.abc import Mapping
from collections.abc import Sequence
from decimal import Decimal
from urllib.parse import quote

# Rest.li reserves these characters inside values; they and '%' become %XX first.
_RESERVED = frozenset("(:),'%")
# Android's Uri.encode keeps these (plus '%', so the rest.li escapes survive).
_URI_SAFE = "-_.!~*'()%"


def encode(value: object) -> str:
    """Encode records as `(k:v)`, lists as `List(a,b)`, strings escaped and percent-encoded."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("Rest.li values must be finite numbers.")
        # Plain decimal notation: an exponent's '+' would read as a space in a URL.
        return format(Decimal(repr(value)), "f")
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, Mapping):
        parts = []
        for key, item in value.items():
            # Keys are written verbatim, as the app does, so they must be plain identifiers.
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", key):
                raise ValueError("Rest.li record keys must be identifiers.")
            if item is not None:
                parts.append(f"{key}:{encode(item)}")
        return "(" + ",".join(parts) + ")"
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return "List(" + ",".join(encode(item) for item in value) + ")"
    raise ValueError(f"Rest.li cannot encode {type(value).__name__} values.")


def _string(value: str) -> str:
    if not value:
        return "''"
    escaped = "".join(f"%{ord(ch):02X}" if ch in _RESERVED else ch for ch in value)
    return quote(escaped, safe=_URI_SAFE)
