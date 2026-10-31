"""Publish and manage the account's own posts with the app's content-creation operations.

Posts are shares: GraphQL `ContentCreationShares` creates one (now or scheduled),
`UpdateContentCreationShares` edits it and `DeleteContentcreationSharesByUrn` deletes it.
Instant reposts are the `voyagerFeedDashReposts` rest.li resource; comment control is the
social detail's `updateCommentsRestrictions` action. Every write is sent once.
"""

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from ...exceptions import UnconfirmedWrite
from ...models._json import obj
from ...models._json import string
from ...models.comments import Mention
from ...models.pagination import Cursor
from ...models.pagination import Page
from ...models.posts import CommentScope
from ...models.posts import Document
from ...models.posts import Image
from ...models.posts import LinkPreview
from ...models.posts import NewPoll
from ...models.posts import Video
from ...models.posts import Visibility
from ...models.posts_results import Repost
from ...models.posts_results import ScheduledPost
from ...models.posts_results import SharedPost
from ...transport.voyager import GraphQLQuery
from ...transport.voyager import Voyager
from .. import paging
from .. import threads
from . import payloads
from .media import PostMedia
from .media import create_gallery
from .media import create_poll

CREATE = GraphQLQuery(
    "voyagerContentcreationDashShares.b204104430581f83625ea92a74bf7aa4", "ContentCreationShares"
)
UPDATE = GraphQLQuery(
    "voyagerContentcreationDashShares.14eb3970f345c9c1128e0d57197cbf55",
    "UpdateContentCreationShares",
)
DELETE = GraphQLQuery(
    "voyagerContentcreationDashShares.3f82a2271a8c6a93dae7661d0e57ed26",
    "DeleteContentcreationSharesByUrn",
)
SCHEDULED = GraphQLQuery(
    "voyagerContentcreationDashSharePreviews.272c771715d3b231b34514af90ead86b",
    "ContentCreationSharePreviewsByShareLifeCycleState",
)
REPOSTS = "voyagerFeedDashReposts"
REPOST_DECORATION = "com.linkedin.voyager.dash.deco.feed.repost.Repost-3"
SOCIAL_DETAILS = "voyagerSocialDashSocialDetails"

_SHARE = re.compile(r"urn:li:(share|ugcPost):[0-9]+")
_REPOST = re.compile(r"urn:li:fsd_repost:urn:li:[A-Za-z]+:\(urn:li:[A-Za-z]+:[0-9]+,[0-9]+\)")

# What one post can carry: an image or a gallery, a video, a document, a poll or a link card.
Attachment = Image | Sequence[Image] | Video | Document | NewPoll | LinkPreview


class Posts:
    """Create, edit, delete, schedule and repost the account's posts.

    `media` uploads files and previews links for attachments.
    """

    def __init__(self, voyager: Voyager) -> None:
        self._voyager = voyager
        self.media = PostMedia(voyager)

    async def create(
        self,
        text: str = "",
        *,
        visibility: Visibility = Visibility.ANYONE,
        comments: CommentScope = CommentScope.ANYONE,
        mentions: Sequence[Mention] = (),
        media: Attachment | None = None,
        publish_at: datetime | None = None,
    ) -> SharedPost:
        """Publish a post now, or schedule it for `publish_at`.

        `media` attaches one thing: one or more `Image`s, a `Video`, a `Document`, a
        `NewPoll` or a `LinkPreview`. Several images first create a gallery, and a poll its
        poll entity; those stay behind if the post itself is then refused.
        """
        entity = _share(text, visibility, comments, mentions, publish_at)
        if media is None and not text.strip():
            raise ValueError("A post needs text or media.")
        if media is not None:
            entity["media"] = await self._attach(media)
        return await self._create(entity)

    async def repost_with_thoughts(
        self,
        share_urn: str,
        text: str,
        *,
        visibility: Visibility = Visibility.ANYONE,
        comments: CommentScope = CommentScope.ANYONE,
        mentions: Sequence[Mention] = (),
    ) -> SharedPost:
        """Share someone's post with your own text above it (the original's share URN)."""
        parent = _share_urn(share_urn)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Repost with thoughts needs text; use repost() otherwise.")
        entity = _share(text, visibility, comments, mentions, None, origin="RESHARE")
        entity["parentUrn"] = parent
        return await self._create(entity)

    async def edit(
        self, share_urn: str, text: str, *, mentions: Sequence[Mention] = ()
    ) -> SharedPost:
        """Replace a post's text and mentions; the app edits nothing else after publishing."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Edited text must not be empty.")
        changes = {"commentary": payloads.commentary(text, mentions)}
        return await self._update(share_urn, changes)

    async def delete(self, share_urn: str) -> None:
        """Delete a published post."""
        await self._voyager.mutate(DELETE, {"resourceKey": _share_urn(share_urn)})

    async def set_comment_scope(self, post_urn: str, scope: CommentScope) -> None:
        """Change who can comment on a published post (its activity or ugcPost thread)."""
        detail = threads.social_detail(threads.post(post_urn))
        await self._voyager.post(
            f"{SOCIAL_DETAILS}/{detail}",
            {"allowedCommentersScope": CommentScope(scope).value},
            {"action": "updateCommentsRestrictions"},
        )

    async def repost(self, share_urn: str) -> Repost:
        """Repost a post instantly, without text; keep the result to undo it."""
        reply = await self._voyager.post(
            REPOSTS, {"rootContentUrn": _share_urn(share_urn)}, {"decorationId": REPOST_DECORATION}
        )
        urn = string(reply.data, "entityUrn") or reply.created_id
        if not urn:
            raise UnconfirmedWrite("LinkedIn's repost reply did not name the repost.")
        return Repost(
            urn=urn,
            root_urn=string(reply.data, "rootContentUrn"),
            message=string(reply.data, "toastMainText"),
            raw=reply.data,
        )

    async def undo_repost(self, repost_urn: str) -> None:
        """Remove an instant repost by its `Repost.urn`."""
        if not isinstance(repost_urn, str) or not _REPOST.fullmatch(repost_urn):
            raise ValueError("A Repost.urn (urn:li:fsd_repost:...) is required.")
        await self._voyager.delete(f"{REPOSTS}/{repost_urn}")

    async def scheduled(
        self, *, count: int = 10, cursor: Cursor | None = None
    ) -> Page[ScheduledPost]:
        """Read one page of the account's scheduled posts, soonest first."""
        if type(count) is not int or not 1 <= count <= 100:
            raise ValueError("count must be between 1 and 100.")
        start, _token = paging.resume(cursor, "posts.scheduled", "SCHEDULED", self._voyager.owner)
        data = await self._voyager.query(
            SCHEDULED, {"shareLifeCycleState": "SCHEDULED", "start": start, "count": count}
        )
        found = paging.collection(data, "contentcreationDashSharePreviewsByShareLifeCycleState")
        return paging.page(
            found,
            ScheduledPost.from_preview,
            "posts.scheduled",
            "SCHEDULED",
            start,
            count,
            self._voyager.owner,
        )

    async def reschedule(self, share_urn: str, publish_at: datetime) -> SharedPost:
        """Move a scheduled post to a new future time."""
        return await self._update(share_urn, {"scheduledAt": payloads.epoch_millis(publish_at)})

    async def cancel_scheduled(self, share_urn: str) -> None:
        """Delete a scheduled post before it is published."""
        await self._voyager.mutate(
            # The app's delete spells it shareLifecycleState; its list uses shareLifeCycleState.
            DELETE,
            {"resourceKey": _share_urn(share_urn), "shareLifecycleState": "SCHEDULED"},
        )

    async def _create(self, entity: dict[str, Any]) -> SharedPost:
        data = await self._voyager.mutate(CREATE, {"entity": entity})
        return _shared(data, "createContentcreationDashShares")

    async def _update(self, share_urn: str, changes: dict[str, Any]) -> SharedPost:
        variables = {"entity": {"resourceKey": _share_urn(share_urn), "entity": changes}}
        data = await self._voyager.mutate(UPDATE, variables)
        return _shared(data, "updateContentcreationDashShares")

    async def _attach(self, media: Attachment) -> dict[str, Any]:
        """The share's media; galleries and polls are created first, as the app does."""
        if isinstance(media, Video):
            return payloads.video(media)
        if isinstance(media, Document):
            return payloads.document(media)
        if isinstance(media, LinkPreview):
            return payloads.reference(media.article_urn, media.original_url)
        if isinstance(media, NewPoll):
            return payloads.reference(await create_poll(self._voyager, media))
        images = (media,) if isinstance(media, Image) else media
        if isinstance(images, Sequence) and images and all(isinstance(i, Image) for i in images):
            if len(images) == 1:
                return payloads.image(images[0])
            member_id = self._voyager.transport.session.member_id
            if not member_id:
                raise ValueError("Call account.me() first so the session knows its member.")
            return payloads.reference(await create_gallery(self._voyager, images, member_id))
        raise ValueError("media must be Image(s), a Video, a Document, a NewPoll or a LinkPreview.")


def _share(
    text: str,
    visibility: Visibility,
    comments: CommentScope,
    mentions: Sequence[Mention],
    publish_at: datetime | None,
    origin: str = "FEED",
) -> dict[str, Any]:
    """A `ShareForCreate` as the share box builds it from the feed."""
    entity: dict[str, Any] = {
        "allowedCommentersScope": CommentScope(comments).value,
        "origin": origin,
        "visibilityDataUnion": {"visibilityType": Visibility(visibility).value},
        "commentary": payloads.commentary(text, mentions),
    }
    if publish_at is not None:
        entity["scheduledAt"] = payloads.epoch_millis(publish_at)
        entity["intendedShareLifeCycleState"] = "SCHEDULED"
    return entity


def _shared(data: dict[str, Any], field: str) -> SharedPost:
    shared = SharedPost.from_reply(obj(data.get(field)))
    if shared is None:
        raise UnconfirmedWrite("LinkedIn's reply did not name the share.")
    return shared


def _share_urn(urn: str) -> str:
    if not isinstance(urn, str) or not _SHARE.fullmatch(urn):
        raise ValueError(
            "A share URN such as urn:li:share:<id> or urn:li:ugcPost:<id> is required."
        )
    return urn
