"""Comments, replies and comment reactions as Voyager's dash `Comment` objects describe them."""

from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from enum import StrEnum
from typing import Any

from ._json import boolean
from ._json import dig
from ._json import integer
from ._json import items
from ._json import obj
from ._json import public_id
from ._json import string
from ._json import text
from .content import Author
from .content import SocialCounts


class CommentSort(StrEnum):
    """The app's two comment orders; the UI labels are in comments."""

    RELEVANCE = "RELEVANCE"  # Most relevant
    RECENT = "REVERSE_CHRONOLOGICAL"  # Most recent


@dataclass(frozen=True, slots=True)
class Mention:
    """A tag inside comment or post text: `urn` covers `length` characters from `start`.

    `urn` is a member's profile URN (`urn:li:fsd_profile:<id>`, as `Author.profile_urn`
    reads it); posts also accept a company (`urn:li:fsd_company:<id>`). Positions count
    Unicode code points, as the app does; the server silently drops a wrong offset.
    """

    urn: str
    start: int
    length: int


@dataclass(frozen=True, slots=True)
class Comment:
    """One comment or reply.

    `urn` (`urn:li:comment:(activity:<post>,<id>)`) is the comment's own social thread: every
    comment operation, reaction and reply addresses it. `entity_urn` is the dash entity form.
    `post_urn` is the post's thread; `parent_urn` is set on replies. `replies` holds only the
    preview the server embeds; `Comments.replies()` pages through all of them.
    `created_at` is in epoch milliseconds. `actions` lists the server's allowed actions,
    such as `EDIT_COMMENT` and `DELETE`.
    """

    urn: str
    entity_urn: str | None
    post_urn: str | None
    parent_urn: str | None
    author: Author | None
    text: str | None
    mentions: tuple[Mention, ...]
    created_at: int | None
    edited: bool | None
    pinned: bool | None
    by_post_author: bool | None
    counts: SocialCounts
    actions: tuple[str, ...]
    can_reply: bool | None = None
    can_react: bool | None = None
    hide_action_urn: str | None = None
    permalink: str | None = None
    replies: tuple["Comment", ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_json(cls, comment: dict[str, Any]) -> "Comment | None":
        """Build a comment from a dash `Comment`; None when it has no comment URN."""
        urn = string(comment, "urn")
        if not urn or not urn.startswith("urn:li:comment:("):
            return None
        social = obj(comment.get("socialDetail"))
        counts = obj(social.get("totalSocialActivityCounts"))
        permissions = obj(social.get("socialPermissions"))
        commenter = comment.get("commenter")
        replies = (cls.from_json(reply) for reply in items(dig(social, "comments", "elements")))
        hide_action = string(comment, "hideCommentActionUrn") or string(
            comment, "hideCommentAction", "entityUrn"
        )
        return cls(
            urn=urn,
            entity_urn=string(comment, "entityUrn"),
            post_urn=_post_urn(urn),
            parent_urn=string(comment, "parentCommentBackendUrn"),
            author=_author(commenter) if isinstance(commenter, dict) else None,
            text=text(comment, "commentary"),
            mentions=_mentions(obj(comment.get("commentary"))),
            created_at=integer(comment, "createdAt"),
            edited=boolean(comment, "edited"),
            pinned=boolean(comment, "pinned"),
            by_post_author=boolean(commenter, "author"),
            counts=SocialCounts.from_json(counts),
            actions=tuple(a for a in comment.get("actions") or () if isinstance(a, str)),
            can_reply=boolean(permissions, "canPostComments"),
            can_react=boolean(permissions, "canReact"),
            hide_action_urn=hide_action,
            permalink=string(comment, "permalink"),
            replies=tuple(reply for reply in replies if reply is not None),
            raw=deepcopy(comment),
        )


def _author(commenter: dict[str, Any]) -> Author:
    """Read a comment's `commenter`; its shape differs from a feed `ActorComponent`."""
    actor = obj(commenter.get("actor"))
    profile = string(actor, "profileUrn", "entityUrn") or string(
        commenter, "actorUnion", "profileUrn"
    )
    subtitle = commenter.get("subtitle")
    url = string(commenter, "navigationUrl")
    return Author(
        urn=string(commenter, "urn"),
        name=text(commenter, "title"),
        headline=subtitle if isinstance(subtitle, str) else text(commenter, "subtitle"),
        profile_urn=profile,
        public_id=public_id(url),
        url=url.split("?", 1)[0] if url else None,
    )


def _mentions(commentary: dict[str, Any]) -> tuple[Mention, ...]:
    found = []
    for attribute in items(commentary.get("attributesV2")):
        start, length = integer(attribute, "start"), integer(attribute, "length")
        detail = obj(attribute.get("detailData"))
        urn = string(detail, "profileMention", "entityUrn") or string(
            detail, "profileFullName", "entityUrn"
        )
        if urn and start is not None and length is not None:
            found.append(Mention(urn, start, length))
    return tuple(found)


def _post_urn(comment_urn: str) -> str | None:
    """The post thread inside `urn:li:comment:(activity:<id>,<comment id>)`."""
    thread = comment_urn.removeprefix("urn:li:comment:(").rpartition(",")[0]
    return f"urn:li:{thread}" if thread and "(" not in thread else None
