"""Read, write and react to comments with the app's Voyager comment operations.

Reads are the conversations GraphQL finders; comments are created with the GraphQL
`CreateComment` mutation the app uses on threaded posts, edited and deleted through the
`voyagerSocialDashNormComments` rest.li resource. Every write is sent once.
"""

from collections.abc import Sequence
from typing import TypeVar

from ...exceptions import ProtocolError
from ...exceptions import UnconfirmedWrite
from ...models._json import dig
from ...models._json import items
from ...models._json import obj
from ...models.comments import Comment
from ...models.comments import CommentSort
from ...models.comments import Mention
from ...models.content import ReactionType
from ...models.feed import ReactionSort
from ...models.feed import Reactor
from ...models.pagination import Cursor
from ...models.pagination import Page
from ...transport.voyager import GraphQLQuery
from ...transport.voyager import Voyager
from .. import paging
from .. import threads
from ..mentions import attributes as mention_attributes
from ..reactions import Reactions
from .urns import CommentUrn

LIST = GraphQLQuery(
    "voyagerSocialDashComments.b3ab21bfb7ad22b2f1bcb3b38149a0cb", "FetchCommentsWithReplySortOrder"
)
# The comment-detail finder: given a comment's social detail it lists that comment's replies.
REPLIES = GraphQLQuery(
    "voyagerSocialDashComments.59bca422f480a4cc0ce56ccd81181488", "FetchComments"
)
SINGLE = GraphQLQuery(
    "voyagerSocialDashComments.8033a0107cfe3b64ffebc9eef95f2f37", "FetchSingleComment"
)
CREATE = GraphQLQuery(
    "voyagerSocialDashNormComments.cd3d2a3fd6c9b2881c7cac32847ec05e", "CreateComment"
)
HIDE = GraphQLQuery(
    "voyagerSocialDashHideCommentAction.42dde3771a51671edde117e558ab9d46", "HideCommentAction"
)
UNHIDE = GraphQLQuery(
    "voyagerSocialDashHideCommentAction.e0b625699dc0ad3e093ac92a0b53dfc0", "UndoHideCommentAction"
)
NORM_COMMENTS = "voyagerSocialDashNormComments"
DECORATION = "com.linkedin.voyager.dash.deco.social.NormComment-38"
# Replies always come oldest first in the app.
REPLY_ORDER = "CHRONOLOGICAL"

T = TypeVar("T")


class Comments:
    """Comments on any post the account can see; editing and deleting only its own."""

    def __init__(self, voyager: Voyager) -> None:
        self._voyager = voyager
        self._reactions = Reactions(voyager)

    async def list(
        self,
        post_urn: str,
        *,
        sort: CommentSort = CommentSort.RELEVANCE,
        count: int = 10,
        cursor: Cursor | None = None,
    ) -> Page[Comment]:
        """Read one page of a post's top-level comments, each with its reply preview."""
        thread, order = threads.post(post_urn), CommentSort(sort)
        scope = f"{thread}|{order.value}"
        start, token = paging.resume(cursor, "comments.list", scope, self._voyager.owner)
        size = _count(count)
        variables = {
            "socialDetailUrn": threads.social_detail(thread),
            "start": start,
            "count": size,
            "paginationToken": token,
            "sortOrder": order.value,
            "replySortOrder": REPLY_ORDER,
        }
        data = await self._voyager.query(LIST, variables)
        found = paging.collection(data, "socialDashCommentsBySocialDetail")
        return paging.page(
            found, Comment.from_json, "comments.list", scope, start, size, self._voyager.owner
        )

    async def replies(
        self, comment_urn: str, *, count: int = 10, cursor: Cursor | None = None
    ) -> Page[Comment]:
        """Read one page of a comment's replies, oldest first."""
        comment = CommentUrn.parse(comment_urn)
        start, token = paging.resume(cursor, "comments.replies", comment.urn, self._voyager.owner)
        size = _count(count)
        variables = {
            "socialDetailUrn": threads.social_detail(comment.urn),
            "start": start,
            "count": size,
            "paginationToken": token,
            "sortOrder": REPLY_ORDER,
        }
        data = await self._voyager.query(REPLIES, variables)
        found = paging.collection(data, "socialDashCommentsBySocialDetail")
        return paging.page(
            found,
            Comment.from_json,
            "comments.replies",
            comment.urn,
            start,
            size,
            self._voyager.owner,
        )

    async def get(self, comment_urn: str) -> Comment:
        """Read one comment or reply; a deleted one raises `OperationRejected`."""
        comment = CommentUrn.parse(comment_urn)
        data = await self._voyager.query(
            SINGLE, {"commentUrn": comment.entity_urn, "updateThreadUrn": comment.post_urn}
        )
        elements = items(dig(data, "socialDashCommentsBySingleComment", "elements"))
        return _comment(elements[0] if elements else None)

    async def create(
        self, post_urn: str, text: str, *, mentions: Sequence[Mention] = ()
    ) -> Comment:
        """Comment on a post; `mentions` tag members inside `text`."""
        return await self._create(threads.post(post_urn), text, mentions)

    async def reply(
        self, comment_urn: str, text: str, *, mentions: Sequence[Mention] = ()
    ) -> Comment:
        """Reply to a top-level comment."""
        return await self._create(CommentUrn.parse(comment_urn).urn, text, mentions)

    async def edit(
        self, comment_urn: str, text: str, *, mentions: Sequence[Mention] = ()
    ) -> Comment:
        """Replace the text of the account's own comment or reply."""
        comment = CommentUrn.parse(comment_urn)
        patch = {"patch": {"$set": {"commentary": _commentary(text, mentions)}}}
        reply = await self._voyager.post(
            f"{NORM_COMMENTS}/{comment.entity_urn}", patch, {"decorationId": DECORATION}
        )
        elements = items(dig(reply.data, "singleComment", "elements"))
        return _comment(elements[0] if elements else None, written=True)

    async def delete(self, comment_urn: str) -> None:
        """Delete the account's own comment (with its replies) or reply."""
        comment = CommentUrn.parse(comment_urn)
        await self._voyager.delete(f"{NORM_COMMENTS}/{comment.entity_urn}")

    async def react(self, comment_urn: str, reaction: ReactionType = ReactionType.LIKE) -> None:
        """React to a comment or reply."""
        await self._reactions.add(CommentUrn.parse(comment_urn).urn, reaction)

    async def change_reaction(self, comment_urn: str, reaction: ReactionType) -> None:
        """Change the account's existing reaction on a comment or reply."""
        await self._reactions.change(CommentUrn.parse(comment_urn).urn, reaction)

    async def unreact(self, comment_urn: str) -> None:
        """Remove the account's reaction from a comment or reply."""
        await self._reactions.remove(CommentUrn.parse(comment_urn).urn)

    async def reactions(
        self,
        comment_urn: str,
        *,
        reaction: ReactionType | None = None,
        sort: ReactionSort = ReactionSort.RELEVANCE,
        count: int = 10,
        cursor: Cursor | None = None,
    ) -> Page[Reactor]:
        """Who reacted to a comment, optionally only one reaction type."""
        thread = CommentUrn.parse(comment_urn).urn
        return await self._reactions.list(
            thread, reaction=reaction, sort=sort, count=count, cursor=cursor
        )

    async def hide(self, comment: Comment) -> None:
        """Hide someone's comment on the account's own post via its `hide_action_urn`."""
        await self._voyager.mutate(HIDE, {"hideCommentActionUrn": _hide_action(comment)})

    async def unhide(self, comment: Comment) -> None:
        """Show a comment hidden with `hide()` again."""
        await self._voyager.mutate(UNHIDE, {"hideCommentActionUrn": _hide_action(comment)})

    async def _create(self, thread_urn: str, text: str, mentions: Sequence[Mention]) -> Comment:
        entity = {"commentary": _commentary(text, mentions), "threadUrn": thread_urn}
        data = await self._voyager.mutate(CREATE, {"entity": entity})
        return _comment(
            dig(data, "createSocialDashNormComments", "entity", "comment"), written=True
        )


def _commentary(text: str, mentions: Sequence[Mention]) -> dict[str, object]:
    """The app's comment `TextViewModel`: plain text plus one attribute per member mention."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Comment text must not be empty.")
    written = mention_attributes(text, mentions, companies=False)
    return {"text": text, "attributesV2": written, "textDirection": "FIRST_STRONG"}


def _comment(value: object, *, written: bool = False) -> Comment:
    comment = Comment.from_json(obj(value))
    if comment is None:
        failure = UnconfirmedWrite if written else ProtocolError
        raise failure("LinkedIn's reply did not contain the comment.")
    return comment


def _hide_action(comment: Comment) -> str:
    if not isinstance(comment, Comment):
        raise ValueError("A Comment read from LinkedIn is required.")
    if not comment.hide_action_urn:
        raise ValueError("LinkedIn offers no hide action for this comment.")
    return comment.hide_action_urn


def _count(count: int) -> int:
    if type(count) is not int or not 1 <= count <= 100:
        raise ValueError("count must be an integer from 1 to 100.")
    return count
