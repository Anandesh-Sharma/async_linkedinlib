"""Feed reads and the viewer's explicit actions on posts.

Unset GraphQL variables are None, which rest.li encoding leaves out, as the app does.
"""

from ...exceptions import ProtocolError
from ...exceptions import UnconfirmedWrite
from ...models._json import items
from ...models.content import Post
from ...models.content import ReactionType
from ...models.feed import CompanyContent
from ...models.feed import FeedSort
from ...models.feed import ProfileActivity
from ...models.feed import ReactionSort
from ...models.feed import Reactor
from ...models.feed import SavedPost
from ...models.pagination import Cursor
from ...models.pagination import Page
from ...transport.voyager import GraphQLQuery
from ...transport.voyager import Voyager
from .. import paging
from ..reactions import Reactions
from . import queries
from . import saved
from . import urns

_PROFILE_QUERIES = {
    ProfileActivity.POSTS: (queries.PROFILE_POSTS, "feedDashProfileUpdatesByMemberShareFeed"),
    ProfileActivity.COMMENTS: (queries.PROFILE_COMMENTS, "feedDashProfileUpdatesByMemberComments"),
    ProfileActivity.REACTIONS: (
        queries.PROFILE_REACTIONS,
        "feedDashProfileUpdatesByMemberReactions",
    ),
}


class Feed:
    """Read feeds, posts, reactors and saved posts; act on posts only when asked.

    Reads never write. Each write is sent once and never retried; a timeout leaves its
    outcome unknown.
    """

    def __init__(self, voyager: Voyager) -> None:
        self._voyager = voyager
        self._reactions = Reactions(voyager)

    async def home(
        self, *, count: int = 10, sort: FeedSort | None = None, cursor: Cursor | None = None
    ) -> Page[Post]:
        """One page of the main feed; recommendation modules are left out of `items`.

        Without `sort` the server uses the member's preference. A sort applies to this
        request only; it does not change the saved preference.
        """
        size = urns.count(count)
        order = FeedSort(sort) if sort is not None else None
        scope = order.value if order else ""
        start, token = paging.resume(cursor, "feed.home", scope, self._voyager.owner)
        variables = {
            "paginationToken": token,
            "start": start,
            "count": size,
            "sortOrder": order.value if order else None,
        }
        data = await self._voyager.query(queries.MAIN_FEED, variables)
        found = paging.collection(data, "feedDashMainFeedByMainFeed")
        return paging.page(
            found, Post.from_update, "feed.home", scope, start, size, self._voyager.owner
        )

    async def get(self, urn: str) -> Post:
        """One post by its activity, ugcPost or share URN.

        The server refuses a missing or deleted post (`OperationRejected`).
        """
        data = await self._voyager.query(
            queries.UPDATE,
            {
                "urnOrNss": urns.backend(urn),
                "commentsCount": 10,
                "likesCount": 10,
                "moduleKey": queries.DETAIL_MODULE,
            },
        )
        found = paging.collection(data, "feedDashUpdatesByBackendUrnOrNss")
        for update in items(found.get("elements")):
            post = Post.from_update(update)
            if post is not None:
                return post
        raise ProtocolError("LinkedIn returned no post for this URN.")

    async def profile(
        self,
        profile_urn: str,
        activity: ProfileActivity = ProfileActivity.POSTS,
        *,
        count: int = 10,
        cursor: Cursor | None = None,
    ) -> Page[Post]:
        """A member's posts, or the posts they commented on or reacted to, newest first.

        For comments and reactions, `Post.context` says what the member did.
        """
        kind = ProfileActivity(activity)
        query, field = _PROFILE_QUERIES[kind]
        profile = urns.profile(profile_urn)
        size = urns.count(count)
        scope = f"{kind.value}:{profile}"
        start, token = paging.resume(cursor, "feed.profile", scope, self._voyager.owner)
        variables = {
            "profileUrn": profile,
            "count": size,
            "paginationToken": token,
            "start": start,
        }
        data = await self._voyager.query(query, variables)
        found = paging.collection(data, field)
        return paging.page(
            found, Post.from_update, "feed.profile", scope, start, size, self._voyager.owner
        )

    async def company(
        self,
        company_urn: str,
        content: CompanyContent = CompanyContent.ALL,
        *,
        count: int = 10,
        cursor: Cursor | None = None,
    ) -> Page[Post]:
        """A company page's posts, optionally only images, videos, documents or articles."""
        page_urn = urns.company_page(company_urn)
        kind = CompanyContent(content)
        size = urns.count(count)
        scope = f"{kind.value}:{page_urn}"
        start, token = paging.resume(cursor, "feed.company", scope, self._voyager.owner)
        variables = {
            "organizationalPageUrn": page_urn,
            "count": size,
            "filter": kind.value,
            "moduleKey": queries.COMPANY_MODULE,
            "paginationToken": token,
            "start": start,
        }
        data = await self._voyager.query(queries.COMPANY_POSTS, variables)
        found = paging.collection(data, "feedDashOrganizationalPageUpdatesByOrganizationalPageFeed")
        return paging.page(
            found, Post.from_update, "feed.company", scope, start, size, self._voyager.owner
        )

    async def reactions(
        self,
        urn: str,
        *,
        reaction: ReactionType | None = None,
        sort: ReactionSort = ReactionSort.RELEVANCE,
        count: int = 10,
        cursor: Cursor | None = None,
    ) -> Page[Reactor]:
        """Who reacted to a post or comment, optionally only one reaction type."""
        return await self._reactions.list(
            urn, reaction=reaction, sort=sort, count=count, cursor=cursor
        )

    async def react(self, urn: str, reaction: ReactionType = ReactionType.LIKE) -> None:
        """Add the viewer's reaction to a post's thread (`Post.urn`)."""
        await self._reactions.add(urn, reaction)

    async def change_reaction(self, urn: str, reaction: ReactionType) -> None:
        """Replace the viewer's existing reaction on a post's thread."""
        await self._reactions.change(urn, reaction)

    async def unreact(self, urn: str) -> None:
        """Remove the viewer's reaction from a post's thread."""
        await self._reactions.remove(urn)

    async def save(self, activity_urn: str) -> None:
        """Save a post for later.

        `activity_urn` is the post's own activity: `Post.urn` when it is an activity URN,
        otherwise `Post.activity_urn` of the post as `get()` returns it.
        """
        await self._set_saved(activity_urn, True)

    async def unsave(self, activity_urn: str) -> None:
        """Remove a post from the saved items; takes the same URN as `save`."""
        await self._set_saved(activity_urn, False)

    async def saved(self, *, count: int = 10, cursor: Cursor | None = None) -> Page[SavedPost]:
        """One page of the viewer's saved posts, most recently saved first."""
        return await saved.read(self._voyager, count, cursor)

    async def hide(self, update_urn: str) -> None:
        """Hide a feed update (`Post.update_urn`) from the viewer's feed, like the app's Hide."""
        await self._send(queries.HIDE, {"updateUrn": urns.update(update_urn)})

    async def undo_hide(self, update_urn: str) -> None:
        """Undo `hide` for the same update URN."""
        await self._send(queries.UNDO_HIDE, {"updateUrn": urns.update(update_urn)})

    async def vote(self, poll_option_urn: str) -> None:
        """Vote for a poll option (`PollOption.urn`)."""
        await self._send(queries.VOTE, {"pollOptionUrn": urns.poll_option(poll_option_urn)})

    async def unvote(self, poll_option_urn: str) -> None:
        """Withdraw the viewer's vote for a poll option."""
        await self._send(queries.UNVOTE, {"pollOptionUrn": urns.poll_option(poll_option_urn)})

    async def _set_saved(self, activity_urn: str, is_saved: bool) -> None:
        # The save state is keyed on the post's activity, as the app's update actions and
        # the saved-posts list name it.
        activity = urns.activity(activity_urn)
        entity = {
            "entity": {
                "saved": is_saved,
                "preDashEntityUrn": f"urn:li:fs_saveAction:(SAVE,{activity})",
            },
            "resourceKey": f"urn:li:fsd_saveState:(SAVE,{activity})",
        }
        await self._send(queries.SAVE_STATE, {"entity": entity})

    async def _send(self, query: GraphQLQuery, variables: dict[str, object]) -> None:
        data = await self._voyager.mutate(query, variables)
        if not data:
            raise UnconfirmedWrite("LinkedIn's reply to the action had no result.")
