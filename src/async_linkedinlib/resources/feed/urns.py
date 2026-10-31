"""Input checks for feed operations; each raises ValueError with the expected form."""

import re

_BACKEND = re.compile(r"urn:li:(activity|ugcPost|share):\d+")
_ACTIVITY = re.compile(r"urn:li:activity:\d+")
_UPDATE = re.compile(r"urn:li:fsd_update:\(.+\)")
_PROFILE = re.compile(r"urn:li:fsd_profile:[A-Za-z0-9_-]+")
_COMPANY = re.compile(r"urn:li:(company|fsd_company|fsd_organizationalPage):(\d+)")

# The app asks for 3 to 10 items at a time; this keeps requests in a modest range.
MAX_COUNT = 50


def backend(urn: str) -> str:
    """A post to read: its activity, ugcPost or share URN."""
    if not isinstance(urn, str) or not _BACKEND.fullmatch(urn):
        raise ValueError(
            "A post URN such as urn:li:activity:<id>, urn:li:ugcPost:<id> or urn:li:share:<id>"
            " is needed."
        )
    return urn


def activity(urn: str) -> str:
    """A post's own activity URN, which its save state is keyed on."""
    if not isinstance(urn, str) or not _ACTIVITY.fullmatch(urn):
        raise ValueError(
            "Saving takes the post's activity URN (urn:li:activity:<id>): Post.urn when it is "
            "an activity, otherwise Post.activity_urn."
        )
    return urn


def update(urn: str) -> str:
    """A feed update URN, as `Post.update_urn` reads it."""
    if not isinstance(urn, str) or not _UPDATE.fullmatch(urn):
        raise ValueError("A feed update URN (urn:li:fsd_update:(...), Post.update_urn) is needed.")
    return urn


def profile(urn: str) -> str:
    """A member profile URN, as `Author.profile_urn` reads it."""
    if not isinstance(urn, str) or not _PROFILE.fullmatch(urn):
        raise ValueError("A profile URN such as urn:li:fsd_profile:<id> is needed.")
    return urn


def company_page(urn: str) -> str:
    """The company's page URN; a company URN names the page with the same ID."""
    match = _COMPANY.fullmatch(urn) if isinstance(urn, str) else None
    if not match:
        raise ValueError("A company URN such as urn:li:company:<id> is needed.")
    return f"urn:li:fsd_organizationalPage:{match.group(2)}"


def poll_option(urn: str) -> str:
    """A poll option URN, as `PollOption.urn` reads it."""
    if not isinstance(urn, str) or not urn.startswith("urn:li:") or len(urn) <= 7:
        raise ValueError("A poll option URN (PollOption.urn) is needed.")
    return urn


def count(value: int) -> int:
    """A page size from 1 to MAX_COUNT."""
    if type(value) is not int or not 1 <= value <= MAX_COUNT:
        raise ValueError(f"count must be an integer from 1 to {MAX_COUNT}.")
    return value
