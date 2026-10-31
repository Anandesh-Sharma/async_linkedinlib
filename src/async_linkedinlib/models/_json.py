"""Small readers for Voyager JSON; absent or mistyped fields read as None."""

from datetime import UTC
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit


def obj(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def items(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def dig(value: object, *keys: str) -> Any:
    """Follow nested object keys; None as soon as one is missing."""
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def string(value: object, *keys: str) -> str | None:
    found = dig(value, *keys)
    return found if isinstance(found, str) else None


def integer(value: object, *keys: str) -> int | None:
    found = dig(value, *keys)
    return found if type(found) is int else None


def boolean(value: object, *keys: str) -> bool | None:
    found = dig(value, *keys)
    return found if isinstance(found, bool) else None


def text(value: object, *keys: str) -> str | None:
    """The string of a Voyager TextViewModel ({"text": ...}) at the given path."""
    return string(value, *keys, "text")


def urn_id(urn: str | None) -> str | None:
    """The last colon-separated part of a simple URN, such as the digits of an activity."""
    if not urn or "(" in urn:
        return None
    return urn.rsplit(":", 1)[-1] or None


def public_id(
    url: str | None, sections: tuple[str, ...] = ("in", "company", "school", "showcase")
) -> str | None:
    """The vanity name in a profile or page URL, such as `ada` in linkedin.com/in/ada?x=1."""
    if not url:
        return None
    parts = [part for part in urlsplit(url).path.split("/") if part]
    return parts[1] if len(parts) >= 2 and parts[0] in sections else None


def epoch_ms(millis: int | None) -> datetime | None:
    """A UTC time from Voyager's epoch milliseconds; zero or absent reads as None."""
    return datetime.fromtimestamp(millis / 1000, UTC) if millis else None
