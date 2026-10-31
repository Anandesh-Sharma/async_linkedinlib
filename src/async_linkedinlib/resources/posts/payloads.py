"""JSON bodies for the app's share models: commentary, share media, multi-photo and poll input.

Field names come from the pegasus `contentcreation` "ForCreate" models; unions are written
as `{"<member>": value}` and text attributes count Unicode code points, as the app does.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from ...models.comments import Mention
from ...models.posts import Document
from ...models.posts import Image
from ...models.posts import NewPoll
from ...models.posts import Video
from ..mentions import attributes

# The composer marks files picked from the device this way (camera captures differ).
_PICKED = "PRE_RECORDED"


def commentary(text: str, mentions: Sequence[Mention] = ()) -> dict[str, Any]:
    """A `TextViewModelForCreate` with one attribute per mention, in text order."""
    if not isinstance(text, str):
        raise ValueError("Post text must be a string.")
    return {"text": text, "attributesV2": attributes(text, mentions)}


def image(item: Image) -> dict[str, Any]:
    body = {
        "category": "IMAGE",
        "mediaUrn": item.media.urn,
        "recipes": list(item.media.recipes),
        "tapTargets": [],
        "nativeMediaSource": _PICKED,
    }
    if item.alt_text:
        body["altText"] = item.alt_text
    return body


def video(item: Video) -> dict[str, Any]:
    return {
        "category": "VIDEO",
        "mediaUrn": item.media.urn,
        "recipes": list(item.media.recipes),
        "tapTargets": [],
        "nativeMediaSource": _PICKED,
    }


def document(item: Document) -> dict[str, Any]:
    return {
        "category": "NATIVE_DOCUMENT",
        "mediaUrn": item.media.urn,
        "recipes": list(item.media.recipes),
        "title": item.title,
    }


def reference(urn: str, original_url: str | None = None) -> dict[str, Any]:
    """Share media pointing at another entity: a multi-photo, a poll or an article."""
    body = {"category": "URN_REFERENCE", "mediaUrn": urn}
    if original_url:
        body["originalUrl"] = original_url
    return body


def multi_photo(images: Sequence[Image], author_urn: str) -> dict[str, Any]:
    """A `MultiPhoto` gallery that one share references."""
    entities = []
    for item in images:
        entity: dict[str, Any] = {
            "mediaUrn": item.media.urn,
            "tapTargets": [],
            "mediaSource": _PICKED,
        }
        if item.alt_text:
            entity["altText"] = item.alt_text
        entities.append(entity)
    return {"authorUrn": author_urn, "entities": entities}


def poll(item: NewPoll) -> dict[str, Any]:
    return {
        "question": item.question,
        "options": list(item.options),
        "duration": item.duration.value,
    }


def epoch_millis(when: datetime) -> int:
    """A future, timezone-aware time as epoch milliseconds."""
    if not isinstance(when, datetime) or when.tzinfo is None:
        raise ValueError("A timezone-aware datetime is required.")
    if when.timestamp() <= datetime.now(when.tzinfo).timestamp():
        raise ValueError("The publish time must be in the future.")
    return int(when.timestamp() * 1000)
