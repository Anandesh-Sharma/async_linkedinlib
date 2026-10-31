import httpx
import pytest

from async_linkedinlib import ProtocolError
from async_linkedinlib import ReactionType
from async_linkedinlib.exceptions import OperationRejected
from async_linkedinlib.models.feed import CompanyContent
from async_linkedinlib.models.feed import FeedSort
from async_linkedinlib.models.feed import ProfileActivity
from async_linkedinlib.models.feed import ReactionSort
from async_linkedinlib.models.pagination import Cursor
from async_linkedinlib.resources.feed import queries

MAIN = "feedDashMainFeedByMainFeed"


async def test_home_sends_the_app_variables_without_device_telemetry(api, fx):
    elements = [fx.module(), fx.make_update("1001"), fx.make_update("1002")]
    client, feed, seen = api(lambda r: fx.graphql(MAIN, fx.collection(elements, total=40)))
    async with client:
        page = await feed.home(count=3)
    assert fx.params(seen[0]) == {
        "queryId": queries.MAIN_FEED.id,
        "queryName": "MainFeed",
    }
    assert fx.variables(seen[0]) == {"start": "0", "count": "3"}
    assert [post.urn for post in page.items] == ["urn:li:activity:1001", "urn:li:activity:1002"]
    assert len(page.raw["elements"]) == 3
    assert page.total == 40
    assert page.next == Cursor("feed.home", "", 3, "page-token")


async def test_home_continues_with_the_token_and_sort(api, fx):
    replies = [
        fx.collection([fx.make_update("1001")], count=5, total=40, token="first"),
        fx.collection([fx.make_update("1002")], start=5, count=5, total=40, token="second"),
    ]
    client, feed, seen = api(lambda r: fx.graphql(MAIN, replies[len(seen) - 1]))
    async with client:
        first = await feed.home(count=5, sort=FeedSort.RECENT)
        second = await feed.home(count=5, sort=FeedSort.RECENT, cursor=first.next)
    assert fx.variables(seen[0]) == {"start": "0", "count": "5", "sortOrder": "REV_CHRON"}
    assert fx.variables(seen[1]) == {
        "paginationToken": "first",
        "start": "5",
        "count": "5",
        "sortOrder": "REV_CHRON",
    }
    assert second.next == Cursor("feed.home", "REV_CHRON", 10, "second")


async def test_cursor_from_another_query_is_refused_before_sending(api, fx):
    client, feed, seen = api(lambda r: fx.graphql(MAIN, fx.collection([fx.make_update()])))
    async with client:
        with pytest.raises(ValueError, match="different operation"):
            await feed.home(sort=FeedSort.RECENT, cursor=Cursor("feed.home", "", 3, "t"))
        with pytest.raises(ValueError, match="different operation"):
            await feed.profile(fx.PROFILE, cursor=Cursor("feed.home", "", 3, "t"))
    assert seen == []


@pytest.mark.parametrize(
    "found",
    [
        {"paging": {"start": 30, "count": 10, "total": 40}, "elements": [{}]},
        {"paging": {"start": 0, "count": 10, "total": 40}, "elements": []},
    ],
)
async def test_last_or_empty_page_has_no_next_cursor(api, fx, found):
    client, feed, seen = api(lambda r: fx.graphql(MAIN, found))
    async with client:
        page = await feed.home(count=10)
    assert page.next is None
    assert page.items == ()


@pytest.mark.parametrize("count", [0, 51, "10", True])
async def test_page_size_is_validated(api, fx, count):
    client, feed, seen = api(lambda r: fx.graphql(MAIN, fx.collection([])))
    async with client:
        with pytest.raises(ValueError, match="count"):
            await feed.home(count=count)
    assert seen == []


async def test_missing_collection_is_a_protocol_error(api, fx):
    client, feed, seen = api(lambda r: fx.graphql(MAIN, None))
    async with client:
        with pytest.raises(ProtocolError):
            await feed.home()


async def test_get_reads_the_detail_update(api, fx):
    field = "feedDashUpdatesByBackendUrnOrNss"
    client, feed, seen = api(lambda r: fx.graphql(field, {"elements": [fx.make_update("7")]}))
    async with client:
        post = await feed.get("urn:li:ugcPost:9")
    assert fx.params(seen[0])["queryId"] == queries.UPDATE.id
    assert fx.variables(seen[0]) == {
        "urnOrNss": "urn:li:ugcPost:9",
        "commentsCount": "10",
        "likesCount": "10",
        "moduleKey": "feed-item:phone",
    }
    assert post.activity_urn == "urn:li:activity:7"


async def test_get_failures(api, fx):
    field = "feedDashUpdatesByBackendUrnOrNss"
    refused = {"data": {field: None}, "errors": [{"message": "Internal error fetching data"}]}
    replies = [httpx.Response(200, json=refused), fx.graphql(field, {"elements": [fx.module()]})]
    client, feed, seen = api(lambda r: replies[len(seen) - 1])
    async with client:
        with pytest.raises(OperationRejected, match="Internal error"):
            await feed.get("urn:li:activity:1")
        with pytest.raises(ProtocolError, match="no post"):
            await feed.get("urn:li:activity:1")
        with pytest.raises(ValueError, match="post URN"):
            await feed.get("urn:li:fsd_update:(urn:li:activity:1,MAIN_FEED)")
    assert len(seen) == 2


@pytest.mark.parametrize(
    ("activity", "query", "field"),
    [
        (ProfileActivity.POSTS, queries.PROFILE_POSTS, "feedDashProfileUpdatesByMemberShareFeed"),
        (
            ProfileActivity.COMMENTS,
            queries.PROFILE_COMMENTS,
            "feedDashProfileUpdatesByMemberComments",
        ),
        (
            ProfileActivity.REACTIONS,
            queries.PROFILE_REACTIONS,
            "feedDashProfileUpdatesByMemberReactions",
        ),
    ],
)
async def test_profile_activity_pages_continue_while_non_empty(api, fx, activity, query, field):
    found = fx.collection([fx.make_update("5")], count=3, token="next")
    client, feed, seen = api(lambda r: fx.graphql(field, found))
    async with client:
        first = await feed.profile(fx.PROFILE, activity, count=3)
        await feed.profile(fx.PROFILE, activity, count=3, cursor=first.next)
    assert fx.params(seen[0]) == {"queryId": query.id, "queryName": query.name}
    assert fx.variables(seen[0]) == {"profileUrn": fx.PROFILE, "count": "3", "start": "0"}
    assert fx.variables(seen[1])["paginationToken"] == "next"
    assert fx.variables(seen[1])["start"] == "3"
    assert first.total is None
    assert first.next == Cursor("feed.profile", f"{activity.value}:{fx.PROFILE}", 3, "next")


async def test_profile_needs_a_profile_urn(api, fx):
    client, feed, seen = api(lambda r: fx.graphql("x", {}))
    async with client:
        with pytest.raises(ValueError, match="profile URN"):
            await feed.profile("urn:li:member:42")
    assert seen == []


async def test_company_addresses_the_page_with_the_company_id(api, fx):
    field = "feedDashOrganizationalPageUpdatesByOrganizationalPageFeed"
    client, feed, seen = api(lambda r: fx.graphql(field, fx.collection([fx.make_update()])))
    async with client:
        page = await feed.company("urn:li:company:77", CompanyContent.VIDEOS, count=4)
        with pytest.raises(ValueError, match="company URN"):
            await feed.company("urn:li:fsd_profile:ACo1")
    assert fx.params(seen[0])["queryId"] == queries.COMPANY_POSTS.id
    assert fx.variables(seen[0]) == {
        "organizationalPageUrn": "urn:li:fsd_organizationalPage:77",
        "count": "4",
        "filter": "VIDEOS",
        "moduleKey": "ORGANIZATION_MEMBER_FEED_PHONE",
        "start": "0",
    }
    assert len(page.items) == 1
    assert len(seen) == 1


async def test_reactions_filter_sort_and_scope(api, fx):
    field = "socialDashReactionsByReactionType"
    reaction = {"actorUrn": "urn:li:fsd_profile:ACoR", "reactionType": "PRAISE"}
    found = fx.collection([reaction], count=2, total=9, token="r1")
    client, feed, seen = api(lambda r: fx.graphql(field, found))
    async with client:
        page = await feed.reactions(
            "urn:li:activity:1",
            reaction=ReactionType.CELEBRATE,
            sort=ReactionSort.NEWEST,
            count=2,
        )
        with pytest.raises(ValueError, match="different operation"):
            await feed.reactions("urn:li:activity:1", cursor=page.next)
    assert fx.params(seen[0])["queryName"] == "FetchSocialDashReactionsByReactionType"
    assert fx.variables(seen[0]) == {
        "threadUrn": "urn:li:activity:1",
        "count": "2",
        "reactionType": "PRAISE",
        "sortOrder": "REVERSE_CHRONOLOGICAL",
        "start": "0",
    }
    assert [r.reaction for r in page.items] == ["PRAISE"]
    assert page.next == Cursor(
        "reactions.list", "urn:li:activity:1|PRAISE|REVERSE_CHRONOLOGICAL", 2, "r1"
    )
    assert len(seen) == 1


async def test_reactions_accept_comment_threads(api, fx):
    field = "socialDashReactionsByReactionType"
    client, feed, seen = api(lambda r: fx.graphql(field, fx.collection([])))
    comment = "urn:li:comment:(activity:1,2)"
    async with client:
        page = await feed.reactions(comment)
        with pytest.raises(ValueError, match="post or comment URN"):
            await feed.reactions("activity:1")
    assert fx.variables(seen[0])["threadUrn"] == comment
    assert fx.variables(seen[0])["sortOrder"] == "RELEVANCE"
    assert page.next is None
