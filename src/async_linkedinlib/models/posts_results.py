"""What posting operations return: the shared post, scheduled posts, reposts, media status."""

from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import Any

from ._json import dig
from ._json import epoch_ms
from ._json import integer
from ._json import obj
from ._json import string
from ._json import text
from .content import Post


@dataclass(frozen=True, slots=True)
class SharedPost:
    """A post the account created or edited.

    `share_urn` (`urn:li:share:<id>` or `urn:li:ugcPost:<id>`) addresses edits, deletion,
    rescheduling and reposts. A published post also has `activity_urn`, the feed `post`
    as the feed reads it, and `social_detail_urn`. A scheduled post has neither until it
    goes out. `message` is the app's confirmation, such as "Post scheduled.".
    """

    share_urn: str
    activity_urn: str | None
    published: bool
    post: Post | None
    social_detail_urn: str | None = None
    message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_reply(cls, reply: dict[str, Any]) -> "SharedPost | None":
        """Read a create or update reply: `{resourceKey, entity: Share}`; None without a URN."""
        share = obj(reply.get("entity"))
        status = obj(share.get("status"))
        update = obj(dig(status, "lifecycleState", "PublishedState"))
        share_urn = (
            string(update, "metadata", "shareUrn")
            or _plain_share(string(share, "entityUrn"))
            or _plain_share(string(reply, "resourceKey"))
        )
        if not share_urn:
            return None
        feedback = obj(status.get("feedbackData"))
        return cls(
            share_urn=share_urn,
            activity_urn=string(update, "metadata", "backendUrn"),
            published=bool(update),
            post=Post.from_update(update) if update else None,
            social_detail_urn=string(update, "socialDetail", "entityUrn"),
            message=string(feedback, "toastComponent", "text")
            or string(feedback, "promptComponentV2", "promptHeader", "mainText"),
            raw=deepcopy(reply),
        )


@dataclass(frozen=True, slots=True)
class ScheduledPost:
    """A post waiting to be published at `publish_at` (UTC).

    `description` is the app's line such as "Posting Mon, Nov 2 at 7:30 AM".
    """

    share_urn: str
    text: str | None
    publish_at: datetime | None
    description: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_preview(cls, preview: dict[str, Any]) -> "ScheduledPost | None":
        """Read a `SharePreview` from the scheduled-posts list; None without its share."""
        mini = obj(preview.get("miniUpdate"))
        share_urn = string(mini, "metadata", "backendUrn")
        if not share_urn:
            return None
        millis = integer(preview, "scheduledAt")
        return cls(
            share_urn=share_urn,
            text=text(mini, "commentary", "commentaryText"),
            publish_at=epoch_ms(millis),
            description=text(preview, "contextualDescription"),
            raw=deepcopy(preview),
        )


@dataclass(frozen=True, slots=True)
class Repost:
    """An instant repost; `urn` (`urn:li:fsd_repost:...`) is what undoing it removes."""

    urn: str
    root_urn: str | None
    message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class MediaStatus:
    """Processing state of an upload: PROCESSING, READY or PROCESSING_FAILED.

    `page_count` is set for processed documents.
    """

    urn: str
    state: str | None
    page_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


def _plain_share(urn: str | None) -> str | None:
    """`urn:li:fsd_share:urn:li:share:<id>` names the share `urn:li:share:<id>`."""
    if not urn:
        return None
    inner = urn.removeprefix("urn:li:fsd_share:")
    return inner if inner.startswith("urn:li:") else None
