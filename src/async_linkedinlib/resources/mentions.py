"""Mentions inside post and comment text, written as the app's text attributes.

Offsets count Unicode code points: a live post on 2026-10-31 with an emoji before a mention
kept the mention only with code-point offsets; UTF-16 offsets were silently dropped.
"""

import re
from collections.abc import Sequence
from typing import Any

from ..models.comments import Mention

# Mention URN kinds and the TextAttributeData union member the app writes for each.
_KINDS = {"fsd_profile": "profileFullName", "fsd_company": "companyName"}
_URN = re.compile(r"urn:li:(fsd_profile|fsd_company):[A-Za-z0-9_-]+")


def attributes(
    text: str, mentions: Sequence[Mention], *, companies: bool = True
) -> list[dict[str, Any]]:
    """One attribute per mention, in text order; mentions may not overlap or leave the text.

    Without `companies`, only members (`urn:li:fsd_profile`) may be mentioned.
    """
    if isinstance(mentions, str | bytes | Mention) or not isinstance(mentions, Sequence):
        raise ValueError("Mentions must be a sequence of Mention values.")
    checked = [_checked(mention, companies) for mention in mentions]
    written = []
    end = 0
    for mention in sorted(checked, key=lambda item: item.start):
        if mention.start < end or mention.start + mention.length > len(text):
            raise ValueError("Mentions must cover separate parts of the text.")
        kind = _KINDS[mention.urn.split(":")[2]]
        written.append(
            {
                "start": mention.start,
                "length": mention.length,
                "detailDataUnion": {kind: mention.urn},
            }
        )
        end = mention.start + mention.length
    return written


def _checked(mention: object, companies: bool) -> Mention:
    if (
        not isinstance(mention, Mention)
        or not isinstance(mention.urn, str)
        or not _URN.fullmatch(mention.urn)
        or (not companies and not mention.urn.startswith("urn:li:fsd_profile:"))
        or type(mention.start) is not int
        or type(mention.length) is not int
        or mention.start < 0
        or mention.length < 1
    ):
        who = "a urn:li:fsd_profile or urn:li:fsd_company" if companies else "a urn:li:fsd_profile"
        raise ValueError(f"A mention needs {who} URN, a start of at least 0 and a positive length.")
    return mention
