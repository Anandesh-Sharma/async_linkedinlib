"""Posts and their authors as Voyager's feed `Update` objects describe them."""

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


class ReactionType(StrEnum):
    """The app's reaction names; the UI labels are in comments."""

    LIKE = "LIKE"
    CELEBRATE = "PRAISE"  # Celebrate
    SUPPORT = "APPRECIATION"  # Support
    LOVE = "EMPATHY"  # Love
    INSIGHTFUL = "INTEREST"  # Insightful
    FUNNY = "ENTERTAINMENT"  # Funny


@dataclass(frozen=True, slots=True)
class Author:
    """A member or organization shown as a post's or comment's actor."""

    urn: str | None
    name: str | None
    headline: str | None = None
    profile_urn: str | None = None
    public_id: str | None = None
    url: str | None = None

    @property
    def is_company(self) -> bool:
        return bool(self.urn and self.urn.startswith(("urn:li:company:", "urn:li:organization:")))

    @classmethod
    def from_actor(cls, actor: dict[str, Any]) -> "Author":
        """Read an `ActorComponent` (feed updates) or comment `commenter` block."""
        attributes = items(dig(actor, "name", "attributesV2"))
        detail = obj(attributes[0].get("detailData")) if attributes else {}
        profile = obj(detail.get("profileFullName"))
        url = string(actor, "navigationContext", "actionTarget")
        return cls(
            urn=string(actor, "backendUrn"),
            name=text(actor, "name"),
            headline=text(actor, "description"),
            profile_urn=string(profile, "entityUrn"),
            public_id=public_id(url),
            url=url.split("?", 1)[0] if url else None,
        )


@dataclass(frozen=True, slots=True)
class SocialCounts:
    """Reaction, comment and repost totals, and the viewer's own reaction.

    `viewer_reaction` is the viewer's reaction name, such as `PRAISE`, when they reacted.
    """

    reactions: int = 0
    comments: int = 0
    reposts: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    viewer_reacted: bool | None = None
    viewer_reaction: str | None = None

    @classmethod
    def from_json(cls, counts: dict[str, Any]) -> "SocialCounts":
        by_type = {
            entry["reactionType"]: entry["count"]
            for entry in items(counts.get("reactionTypeCounts"))
            if isinstance(entry.get("reactionType"), str) and type(entry.get("count")) is int
        }
        return cls(
            reactions=integer(counts, "numLikes") or 0,
            comments=integer(counts, "numComments") or 0,
            reposts=integer(counts, "numShares") or 0,
            by_type=by_type,
            viewer_reacted=boolean(counts, "liked"),
            viewer_reaction=string(counts, "reacted"),
        )


@dataclass(frozen=True, slots=True)
class PollOption:
    """One poll choice; `urn` is what `Feed.vote` and `Feed.unvote` take."""

    urn: str | None
    text: str | None
    votes: int | None = None
    voted: bool = False


@dataclass(frozen=True, slots=True)
class Poll:
    """A post's poll: its question, options with vote counts, and whether it closed."""

    question: str | None
    options: tuple[PollOption, ...]
    voters: int | None = None
    closed: bool | None = None
    multi_select: bool | None = None

    @classmethod
    def from_component(cls, poll: dict[str, Any]) -> "Poll":
        """Read a `PollComponent`; summaries line up with options by position, as in the app."""
        summary = obj(poll.get("pollSummary"))
        totals = items(summary.get("pollOptionSummaries"))
        chosen = summary.get("votedPollOptionUrns")
        voted = (
            {urn for urn in chosen if isinstance(urn, str)} if isinstance(chosen, list) else set()
        )
        options = []
        for index, option in enumerate(items(poll.get("pollOptions"))):
            urn = string(option, "pollOptionUrn")
            votes = integer(totals[index], "voteCount") if index < len(totals) else None
            options.append(PollOption(urn, text(option, "option"), votes, urn in voted))
        return cls(
            question=text(poll, "question"),
            options=tuple(options),
            voters=integer(summary, "uniqueVotersCount"),
            closed=boolean(summary, "closed"),
            multi_select=boolean(poll, "multiSelect"),
        )


@dataclass(frozen=True, slots=True)
class Post:
    """One feed update.

    `urn` is the post's social thread (an activity or ugcPost URN), which reactions and
    comments address. `activity_urn` is the feed activity, which differs when the update is
    a "liked this" or similar context around someone else's post. `update_urn` is the feed
    update itself (`urn:li:fsd_update:(...)`), which hiding addresses. `share_url` is the
    post's public link.
    """

    urn: str
    activity_urn: str | None
    share_urn: str | None
    author: Author | None
    text: str | None
    age: str | None
    visibility: str | None
    context: str | None
    content_type: str | None
    counts: SocialCounts
    can_react: bool | None = None
    can_comment: bool | None = None
    can_share: bool | None = None
    reshared: "Post | None" = None
    update_urn: str | None = None
    share_url: str | None = None
    poll: Poll | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_update(cls, update: dict[str, Any]) -> "Post | None":
        """Build a post from an `Update`; None for modules such as recommendations.

        The full-screen video layout carries the actor and commentary inside its component
        instead of on the update, so both places are read.
        """
        social = obj(update.get("socialDetail"))
        activity = string(update, "metadata", "backendUrn")
        urn = string(social, "threadUrn") or activity
        content = obj(update.get("content"))
        video = obj(content.get("largeSingleVideoComponent"))
        actor = update.get("actor") or video.get("actor")
        if not urn or not isinstance(actor, dict):
            return None
        kinds = [key for key, value in content.items() if value and key.endswith("Component")]
        age = text(actor, "subDescription")
        reshared = update.get("resharedUpdate")
        permissions = obj(social.get("socialPermissions"))
        poll = content.get("pollComponent")
        # The link's query names the viewer as the sharer (rcm=...), so only the path is kept.
        share_url = string(update, "socialContent", "shareUrl")
        return cls(
            urn=urn,
            activity_urn=activity,
            share_urn=string(update, "metadata", "shareUrn"),
            author=Author.from_actor(actor),
            text=text(update, "commentary", "text") or text(video, "commentary"),
            age=(age.split("•", 1)[0].strip() or None) if age else None,
            visibility=string(update, "metadata", "shareAudience"),
            context=text(update, "header", "text"),
            content_type=kinds[0].removesuffix("Component") if kinds else None,
            counts=SocialCounts.from_json(obj(social.get("totalSocialActivityCounts"))),
            can_react=boolean(permissions, "canReact"),
            can_comment=boolean(permissions, "canPostComments"),
            can_share=boolean(permissions, "canShare"),
            reshared=cls.from_update(reshared) if isinstance(reshared, dict) else None,
            update_urn=string(update, "entityUrn"),
            share_url=share_url.split("?", 1)[0] if share_url else None,
            poll=Poll.from_component(poll) if isinstance(poll, dict) else None,
            raw=deepcopy(update),
        )
