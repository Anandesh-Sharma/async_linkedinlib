import httpx
import pytest

from async_linkedinlib import ProtocolError
from async_linkedinlib import ReactionType
from async_linkedinlib.exceptions import OperationRejected
from async_linkedinlib.models.comments import CommentSort
from async_linkedinlib.models.comments import Mention
from async_linkedinlib.models.pagination import Cursor
from async_linkedinlib.resources.comments.resource import LIST
from async_linkedinlib.resources.comments.resource import REPLIES
from async_linkedinlib.resources.comments.resource import SINGLE
from async_linkedinlib.resources.reactions import LIST as REACTIONS

SOCIAL_DETAIL = (
    "urn:li:fsd_socialDetail:(urn:li:activity:1000,urn:li:activity:1000,urn:li:highlightedReply:-)"
)


def reply_with(field, body):
    return lambda request: httpx.Response(200, json={"data": {field: body}})


async def test_list_sends_the_app_finder_and_parses_comments(api, payloads):
    reply = payloads.make_comment("2002", "A reply", parent="2001")
    top = payloads.make_comment("2001", "Test hello", replies=(reply,), reacted="PRAISE")
    page_body = payloads.collection([top], start=0, total=3, token="opaque-token")
    client, comments, seen = api(reply_with("socialDashCommentsBySocialDetail", page_body))
    async with client:
        page = await comments.list(payloads.POST, count=1)

    request = seen[0]
    assert request.method == "GET"
    assert request.url.path == "/voyager/api/graphql"
    assert payloads.graphql_params(request)["queryId"] == LIST.id
    assert payloads.graphql_params(request)["queryName"] == "FetchCommentsWithReplySortOrder"
    assert payloads.variables(request) == {
        "socialDetailUrn": SOCIAL_DETAIL,
        "start": "0",
        "count": "1",
        "sortOrder": "RELEVANCE",
        "replySortOrder": "CHRONOLOGICAL",
    }
    assert page.total == 3
    assert page.next == Cursor("comments.list", f"{payloads.POST}|RELEVANCE", 1, "opaque-token")
    comment = page.items[0]
    assert comment.urn == payloads.comment_urn("2001")
    assert comment.entity_urn == payloads.entity_urn("2001")
    assert comment.post_urn == payloads.POST
    assert comment.parent_urn is None
    assert comment.text == "Test hello"
    assert comment.mentions == (Mention(payloads.PROFILE, 0, 4),)
    assert comment.author is not None
    assert comment.author.name == "Test Member"
    assert comment.author.headline == "Fixture headline"
    assert comment.author.profile_urn == payloads.PROFILE
    assert comment.author.public_id == "test-member"
    assert comment.author.url == "https://www.linkedin.com/in/test-member"
    assert comment.by_post_author is True
    assert comment.counts.reactions == 2
    assert comment.counts.comments == 1
    assert comment.counts.viewer_reaction == "PRAISE"
    assert comment.actions == ("SHARE_VIA", "EDIT_COMMENT", "DELETE")
    assert comment.can_reply is True and comment.can_react is True
    assert comment.created_at == 1700000000000
    assert comment.replies[0].parent_urn == payloads.comment_urn("2001")
    assert comment.raw["urn"] == comment.urn


async def test_next_page_sends_start_and_token_and_ends_at_total(api, payloads):
    body = payloads.collection([payloads.make_comment("2003")], start=1, total=2, token=None)
    client, comments, seen = api(reply_with("socialDashCommentsBySocialDetail", body))
    cursor = Cursor("comments.list", f"{payloads.POST}|REVERSE_CHRONOLOGICAL", 1, "opaque-token")
    async with client:
        page = await comments.list(payloads.POST, sort=CommentSort.RECENT, count=1, cursor=cursor)
    sent = payloads.variables(seen[0])
    assert sent["start"] == "1"
    assert sent["paginationToken"] == "opaque-token"
    assert sent["sortOrder"] == "REVERSE_CHRONOLOGICAL"
    assert page.next is None
    assert len(page.items) == 1


async def test_cursor_from_another_query_is_refused_before_sending(api, payloads):
    client, comments, seen = api(lambda request: httpx.Response(500))
    relevance = Cursor("comments.list", f"{payloads.POST}|RELEVANCE", 10, "t")
    async with client:
        with pytest.raises(ValueError):
            await comments.list(payloads.POST, sort=CommentSort.RECENT, cursor=relevance)
        with pytest.raises(ValueError):
            await comments.replies(payloads.comment_urn("2001"), cursor=relevance)
        with pytest.raises(ValueError):
            await comments.list("urn:li:activity:1001", cursor=relevance)
    assert seen == []


async def test_replies_page_through_the_comment_social_detail(api, payloads):
    body = payloads.collection(
        [payloads.make_comment("2002", parent="2001")], start=0, total=2, token=None
    )
    client, comments, seen = api(reply_with("socialDashCommentsBySocialDetail", body))
    async with client:
        page = await comments.replies(payloads.entity_urn("2001"), count=1)
    request = seen[0]
    assert payloads.graphql_params(request)["queryId"] == REPLIES.id
    thread = payloads.comment_urn("2001")
    assert payloads.variables(request) == {
        "socialDetailUrn": f"urn:li:fsd_socialDetail:({thread},{thread},urn:li:highlightedReply:-)",
        "start": "0",
        "count": "1",
        "sortOrder": "CHRONOLOGICAL",
    }
    assert page.next == Cursor("comments.replies", thread, 1, None)
    assert page.items[0].parent_urn == thread


async def test_get_reads_one_comment_by_its_entity_urn(api, payloads):
    body = {"elements": [payloads.make_comment("2001")]}
    client, comments, seen = api(reply_with("socialDashCommentsBySingleComment", body))
    async with client:
        comment = await comments.get(payloads.comment_urn("2001"))
    assert payloads.graphql_params(seen[0])["queryId"] == SINGLE.id
    assert payloads.variables(seen[0]) == {
        "commentUrn": payloads.entity_urn("2001"),
        "updateThreadUrn": payloads.POST,
    }
    assert comment.urn == payloads.comment_urn("2001")


async def test_get_of_a_deleted_comment_raises_the_server_rejection(api, payloads):
    body = {"data": {"socialDashCommentsBySingleComment": None}, "errors": [{"message": "null"}]}
    client, comments, _ = api(lambda request: httpx.Response(200, json=body))
    async with client:
        with pytest.raises(OperationRejected):
            await comments.get(payloads.comment_urn("2001"))


async def test_reactions_list_reads_who_reacted_with_a_type_filter(api, payloads):
    reaction = {
        "actorUrn": payloads.PROFILE,
        "reactionType": "INTEREST",
        "reactorLockup": {
            "title": {"text": "Test Member"},
            "subtitle": {"text": "Fixture headline"},
            "navigationUrl": "https://www.linkedin.com/in/ACoTestProfile",
        },
    }
    body = payloads.collection([reaction, {"reactionType": "LIKE"}], start=0, total=1, token="r")
    client, comments, seen = api(reply_with("socialDashReactionsByReactionType", body))
    async with client:
        page = await comments.reactions(
            payloads.comment_urn("2001"), reaction=ReactionType.INSIGHTFUL
        )
    assert payloads.graphql_params(seen[0])["queryId"] == REACTIONS.id
    assert payloads.variables(seen[0]) == {
        "threadUrn": payloads.comment_urn("2001"),
        "start": "0",
        "count": "10",
        "reactionType": "INTEREST",
        "sortOrder": "RELEVANCE",
    }
    assert len(page.items) == 1
    item = page.items[0]
    assert item.reaction == "INTEREST"
    assert item.name == "Test Member"
    assert item.headline == "Fixture headline"
    assert item.urn == payloads.PROFILE
    assert page.next is None


@pytest.mark.parametrize(
    "body",
    [
        {"data": {}},
        {"data": {"socialDashCommentsBySocialDetail": {"paging": {"total": 1}}}},
        {"data": {"socialDashCommentsBySocialDetail": []}},
    ],
)
async def test_malformed_list_reply_raises_protocol_error(api, payloads, body):
    client, comments, _ = api(lambda request: httpx.Response(200, json=body))
    async with client:
        with pytest.raises(ProtocolError):
            await comments.list(payloads.POST)


async def test_comments_without_a_comment_urn_are_skipped(api, payloads):
    body = payloads.collection([{"entityUrn": "x"}, payloads.make_comment()], start=0, total=2)
    client, comments, _ = api(reply_with("socialDashCommentsBySocialDetail", body))
    async with client:
        page = await comments.list(payloads.POST, count=2)
    assert [comment.urn for comment in page.items] == [payloads.comment_urn("2001")]
    assert page.next is None


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.list("urn:li:comment:(activity:1000,1)"),
        lambda c: c.list("activity:1000"),
        lambda c: c.list("urn:li:activity:1000", count=0),
        lambda c: c.list("urn:li:activity:1000", count=101),
        lambda c: c.list("urn:li:activity:1000", sort="NEWEST"),
        lambda c: c.replies("urn:li:activity:1000"),
        lambda c: c.get("urn:li:comment:(1000,2001)"),
        lambda c: c.reactions("urn:li:comment:(activity:1000,2001)", reaction="WOW"),
    ],
)
async def test_bad_read_input_raises_value_error_without_a_request(api, call):
    client, comments, seen = api(lambda request: httpx.Response(500))
    async with client:
        with pytest.raises(ValueError):
            await call(comments)
    assert seen == []
