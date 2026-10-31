"""What a new post can carry: audience, comment control and one attachment.

Mentions use `models.comments.Mention`: a member (`urn:li:fsd_profile:<id>`) or company
(`urn:li:fsd_company:<id>`) URN covering `length` code points of the text from `start`.
"""

from dataclasses import dataclass
from dataclasses import field
from enum import StrEnum
from typing import Any


class Visibility(StrEnum):
    """Who can see a post; the app's share box offers these two for members."""

    ANYONE = "ANYONE"
    CONNECTIONS_ONLY = "CONNECTIONS_ONLY"


class CommentScope(StrEnum):
    """Who can comment; the UI labels are Anyone, Connections only and No one."""

    ANYONE = "ALL"
    CONNECTIONS_ONLY = "CONNECTIONS_ONLY"
    NOBODY = "NONE"


class PollDuration(StrEnum):
    """How long a poll stays open, as the poll composer offers."""

    ONE_DAY = "ONE_DAY"
    THREE_DAYS = "THREE_DAYS"
    ONE_WEEK = "ONE_WEEK"
    TWO_WEEKS = "TWO_WEEKS"


class MediaKind(StrEnum):
    """The kind of file uploaded for a post, named by the app's upload use case."""

    IMAGE = "IMAGE_SHARING"
    VIDEO = "VIDEO_SHARING"
    DOCUMENT = "DOCUMENT_SHARING"


@dataclass(frozen=True, slots=True)
class UploadedMedia:
    """A file stored for a post (`urn:li:digitalmediaAsset:<id>`), not yet attached.

    `recipes` are the processing recipes LinkedIn assigned; the share repeats them.
    LinkedIn's app offers no way to delete an upload that is never posted.
    """

    urn: str
    kind: MediaKind
    recipes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Image:
    """An uploaded image to post, with optional alternative text for screen readers."""

    media: UploadedMedia
    alt_text: str | None = None

    def __post_init__(self) -> None:
        _check_media(self.media, MediaKind.IMAGE)


@dataclass(frozen=True, slots=True)
class Video:
    """An uploaded video to post."""

    media: UploadedMedia

    def __post_init__(self) -> None:
        _check_media(self.media, MediaKind.VIDEO)


@dataclass(frozen=True, slots=True)
class Document:
    """An uploaded PDF or slide document to post; the app requires a title for it."""

    media: UploadedMedia
    title: str

    def __post_init__(self) -> None:
        _check_media(self.media, MediaKind.DOCUMENT)
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("A document post needs a title.")


@dataclass(frozen=True, slots=True)
class NewPoll:
    """A poll for a new post, within the composer's limits.

    The question has at most 140 characters; two to five options have at most 30 each.
    """

    question: str
    options: tuple[str, ...]
    duration: PollDuration = PollDuration.ONE_WEEK

    def __post_init__(self) -> None:
        if not _filled(self.question, 140):
            raise ValueError("A poll needs a question of at most 140 characters.")
        options = tuple(self.options)
        if not 2 <= len(options) <= 5 or not all(_filled(option, 30) for option in options):
            raise ValueError("A poll needs two to five options of at most 30 characters.")
        object.__setattr__(self, "options", options)
        object.__setattr__(self, "duration", PollDuration(self.duration))


@dataclass(frozen=True, slots=True)
class LinkPreview:
    """The article card LinkedIn builds for a URL; attach it to share the link.

    `article_urn` (`urn:li:article:<id>`) is what the share references; `url` is the
    address that was previewed. `original_url` is set when LinkedIn names the link
    differently; the share then carries it, as the app does.
    """

    url: str
    article_urn: str
    title: str | None = None
    subtitle: str | None = None
    original_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


def _check_media(media: UploadedMedia, kind: MediaKind) -> None:
    if not isinstance(media, UploadedMedia) or media.kind is not kind:
        raise ValueError(f"An uploaded {kind.name.lower()} is required.")


def _filled(value: object, limit: int) -> bool:
    """Non-blank text within `limit` UTF-16 units, as the app's validators count."""
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value.encode("utf-16-le")) <= limit * 2
    )
