"""Reactions on any social thread: a post's activity or ugcPost URN, or a comment URN."""

from ..models.content import ReactionType
from ..models.feed import ReactionSort
from ..models.feed import Reactor
from ..models.pagination import Cursor
from ..models.pagination import Page
from ..transport.voyager import GraphQLQuery
from ..transport.voyager import Voyager
from . import paging
from . import threads

CREATE = GraphQLQuery(
    "voyagerSocialDashReactions.fd68eadaf15da416b0d839e21399b763", "CreateSocialDashReaction"
)
UPDATE = GraphQLQuery(
    "voyagerSocialDashReactions.846a42c007e6a1741763e9f23956ea0b", "UpdateSocialDashReaction"
)
DELETE = GraphQLQuery(
    "voyagerSocialDashReactions.315cef4773de8e3a0ddad7655cc1685f", "DeleteSocialDashReaction"
)
# conversations/reactionsdetail/ReactionsDetailRepository$$ExternalSyntheticLambda0
LIST = GraphQLQuery(
    "voyagerSocialDashReactions.e996ddaa8544fdbec4f17d40ad2d089a",
    "FetchSocialDashReactionsByReactionType",
)
# The reactions screen pages 10 at a time; larger pages were verified up to 50.
MAX_COUNT = 50


class Reactions:
    """The viewer's reaction on one thread, and who reacted; each write is sent once."""

    def __init__(self, voyager: Voyager) -> None:
        self._voyager = voyager

    async def add(self, thread_urn: str, reaction: ReactionType = ReactionType.LIKE) -> None:
        await self._voyager.mutate(
            CREATE,
            {
                "threadUrn": threads.thread(thread_urn),
                "entity": {"reactionType": ReactionType(reaction).value},
            },
        )

    async def change(self, thread_urn: str, reaction: ReactionType) -> None:
        await self._voyager.mutate(
            UPDATE,
            {
                "threadUrn": threads.thread(thread_urn),
                "newReactionType": ReactionType(reaction).value,
            },
        )

    async def remove(self, thread_urn: str) -> None:
        await self._voyager.mutate(DELETE, {"threadUrn": threads.thread(thread_urn)})

    async def list(
        self,
        thread_urn: str,
        *,
        reaction: ReactionType | None = None,
        sort: ReactionSort = ReactionSort.RELEVANCE,
        count: int = 10,
        cursor: Cursor | None = None,
    ) -> Page[Reactor]:
        """One page of who reacted to a post or comment, optionally of one reaction type."""
        thread = threads.thread(thread_urn)
        kind = ReactionType(reaction).value if reaction is not None else None
        order = ReactionSort(sort)
        if type(count) is not int or not 1 <= count <= MAX_COUNT:
            raise ValueError(f"count must be an integer from 1 to {MAX_COUNT}.")
        # A pagination token pins its query, so the type and order belong to the scope.
        scope = f"{thread}|{kind or ''}|{order.value}"
        owner = self._voyager.owner
        start, token = paging.resume(cursor, "reactions.list", scope, owner)
        variables = {
            "threadUrn": thread,
            "count": count,
            "paginationToken": token,
            "reactionType": kind,
            "sortOrder": order.value,
            "start": start,
        }
        data = await self._voyager.query(LIST, variables)
        found = paging.collection(data, "socialDashReactionsByReactionType")
        return paging.page(
            found, Reactor.from_reaction, "reactions.list", scope, start, count, owner
        )
