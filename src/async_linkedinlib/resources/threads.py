"""Social threads: the post and comment URNs that reactions and comment lists address."""

import re

_POST = re.compile(r"urn:li:(activity|ugcPost):[0-9]+")
_COMMENT = re.compile(r"urn:li:comment:\((activity|ugcPost):[0-9]+,[0-9]+\)")


def post(urn: str) -> str:
    """A post's social thread: `urn:li:activity:<id>` or `urn:li:ugcPost:<id>` (`Post.urn`)."""
    if not isinstance(urn, str) or not _POST.fullmatch(urn):
        raise ValueError(
            "A post URN such as urn:li:activity:<id> or urn:li:ugcPost:<id> is needed."
        )
    return urn


def thread(urn: str) -> str:
    """A reactable thread: a post URN or `urn:li:comment:(activity:<post>,<id>)`."""
    if isinstance(urn, str) and _COMMENT.fullmatch(urn):
        return urn
    if not isinstance(urn, str) or not _POST.fullmatch(urn):
        raise ValueError("A post or comment URN such as urn:li:activity:<id> is needed.")
    return urn


def social_detail(thread_urn: str) -> str:
    """The social detail of a thread: it lists a post's comments or a comment's replies and
    carries the thread's comment settings."""
    return f"urn:li:fsd_socialDetail:({thread_urn},{thread_urn},urn:li:highlightedReply:-)"
