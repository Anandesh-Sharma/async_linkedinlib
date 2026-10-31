"""Feed options and the feed results that are not posts: reactors and saved posts."""

from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from enum import StrEnum
from typing import Any

from ._json import dig
from ._json import items
from ._json import obj
from ._json import string
from ._json import text
from .content import Author


class FeedSort(StrEnum):
    """The main feed's orders (pegasus `dash/feed/SortOrder`); UI labels are in comments."""

    RELEVANCE = "RELEVANCE"  # Top
    RECENT = "REV_CHRON"  # Recent
    MEMBER_SETTING = "MEMBER_SETTING"  # the member's saved preference


class ProfileActivity(StrEnum):
    """The activity tabs of a member's profile."""

    POSTS = "POSTS"
    COMMENTS = "COMMENTS"
    REACTIONS = "REACTIONS"


class CompanyContent(StrEnum):
    """Which of a company page's posts to list (pegasus `OrganizationalPageFeedFilterType`)."""

    ALL = "ALL"
    IMAGES = "IMAGES"
    VIDEOS = "VIDEOS"
    DOCUMENTS = "DOCUMENTS"
    ARTICLES = "ARTICLES"


class ReactionSort(StrEnum):
    """The reactions list orders (pegasus `ReactionSortOrder`); UI labels are in comments."""

    RELEVANCE = "RELEVANCE"  # Most relevant
    NEWEST = "REVERSE_CHRONOLOGICAL"  # Newest first
    OLDEST = "CHRONOLOGICAL"  # Oldest first


@dataclass(frozen=True, slots=True)
class Reactor:
    """Someone who reacted to a post or comment.

    `urn` is the reactor's profile (`urn:li:fsd_profile:<id>`) or page URN; `reaction` is the
    reaction name, such as `LIKE` or `PRAISE`; `degree` is the network label, such as `2nd`.
    """

    urn: str | None
    reaction: str | None
    name: str | None
    headline: str | None
    degree: str | None
    url: str | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_reaction(cls, reaction: dict[str, Any]) -> "Reactor | None":
        """Read a dash `Reaction` with its `reactorLockup` card; None without a reactor."""
        if not string(reaction, "actorUrn"):
            return None
        lockup = obj(reaction.get("reactorLockup"))
        url = string(lockup, "navigationUrl")
        return cls(
            urn=string(reaction, "actorUrn"),
            reaction=string(reaction, "reactionType"),
            name=text(lockup, "title"),
            headline=text(lockup, "subtitle"),
            degree=text(lockup, "label"),
            url=url.split("?", 1)[0] if url else None,
            raw=deepcopy(reaction),
        )


@dataclass(frozen=True, slots=True)
class SavedPost:
    """A post in the viewer's saved items.

    `urn` is the post's activity URN, which `Feed.unsave` takes. The list shows a summary
    card, so `text` may be shortened; `Feed.get(urn)` reads the full post.
    """

    urn: str
    author: Author | None
    text: str | None
    age: str | None
    url: str | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_result(cls, result: dict[str, Any]) -> "SavedPost | None":
        """Read a search `EntityResultViewModel` from the saved-posts list."""
        urn = string(result, "trackingUrn")
        if not urn:
            return None
        attributes = items(dig(result, "image", "attributes"))
        detail = obj(attributes[0].get("detailData")) if attributes else {}
        author_url = string(result, "actorNavigationUrl")
        age = text(result, "secondarySubtitle")
        url = string(result, "navigationUrl")
        return cls(
            urn=urn,
            author=Author(
                urn=string(result, "actorTrackingUrn"),
                name=text(result, "title"),
                headline=text(result, "primarySubtitle"),
                profile_urn=string(detail, "nonEntityProfilePicture", "profile", "entityUrn"),
                url=author_url.split("?", 1)[0] if author_url else None,
            ),
            text=text(result, "summary"),
            age=(age.split("•", 1)[0].strip() or None) if age else None,
            url=url.split("?", 1)[0] if url else None,
            raw=deepcopy(result),
        )
