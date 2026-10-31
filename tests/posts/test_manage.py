import httpx
import pytest

from async_linkedinlib.exceptions import ProtocolError
from async_linkedinlib.models.pagination import Cursor
from async_linkedinlib.models.posts import CommentScope
from async_linkedinlib.resources.posts.resource import SCHEDULED

REPOST = "urn:li:fsd_repost:urn:li:instantRepost:(urn:li:share:2000,8000)"
DECORATION = "com.linkedin.voyager.dash.deco.feed.repost.Repost-3"


async def test_repost_posts_the_root_share_and_keeps_the_repost_urn(api, payloads):
    data = {
        "entityUrn": REPOST,
        "rootContentUrn": payloads.SHARE,
        "toastMainText": "Repost successful.",
    }
    client, posts, seen = api(httpx.Response(201, json=data))
    async with client:
        repost = await posts.repost(payloads.SHARE)
    request = seen[0]
    assert request.method == "POST"
    assert request.url.path == "/voyager/api/voyagerFeedDashReposts"
    assert payloads.params(request) == {"decorationId": DECORATION}
    assert payloads.body(request) == {"rootContentUrn": payloads.SHARE}
    assert (repost.urn, repost.root_urn, repost.message) == (
        REPOST,
        payloads.SHARE,
        "Repost successful.",
    )


async def test_repost_falls_back_to_the_created_id_header(api, payloads):
    client, posts, _ = api(httpx.Response(201, headers={"x-restli-id": REPOST}))
    async with client:
        repost = await posts.repost(payloads.SHARE)
    assert repost.urn == REPOST
    assert repost.root_urn is None


async def test_repost_reply_without_a_urn_is_a_protocol_error(api, payloads):
    client, posts, _ = api(httpx.Response(201, json={}))
    async with client:
        with pytest.raises(ProtocolError):
            await posts.repost(payloads.SHARE)


async def test_undo_repost_deletes_the_repost_entity(api):
    client, posts, seen = api(httpx.Response(204))
    async with client:
        assert await posts.undo_repost(REPOST) is None
    assert seen[0].method == "DELETE"
    assert seen[0].url.raw_path == f"/voyager/api/voyagerFeedDashReposts/{REPOST}".encode()


async def test_comment_scope_updates_the_posts_social_detail(api, payloads):
    client, posts, seen = api(httpx.Response(200))
    async with client:
        await posts.set_comment_scope(payloads.ACTIVITY, CommentScope.CONNECTIONS_ONLY)
    request = seen[0]
    assert request.method == "POST"
    assert (
        request.url.raw_path
        == (
            f"/voyager/api/voyagerSocialDashSocialDetails/{payloads.SOCIAL_DETAIL}"
            "?action=updateCommentsRestrictions"
        ).encode()
    )
    assert payloads.body(request) == {"allowedCommentersScope": "CONNECTIONS_ONLY"}


@pytest.mark.parametrize(
    "call",
    [
        lambda p: p.repost("urn:li:activity:1000"),
        lambda p: p.undo_repost("urn:li:share:2000"),
        lambda p: p.undo_repost("urn:li:fsd_repost:x/../../me"),
        lambda p: p.set_comment_scope("urn:li:share:2000", CommentScope.NOBODY),
        lambda p: p.set_comment_scope("urn:li:activity:1000", "EVERYONE"),
        lambda p: p.scheduled(count=0),
        lambda p: p.scheduled(count=101),
    ],
)
async def test_invalid_calls_send_nothing(api, call):
    client, posts, seen = api()
    async with client:
        with pytest.raises(ValueError):
            await call(posts)
    assert seen == []


def preview(share_id: str, millis: int) -> dict:
    return {
        "scheduledAt": millis,
        "contextualDescription": {"text": "Posting Mon, Nov 2 at 7:30 AM"},
        "miniUpdate": {
            "metadata": {"backendUrn": f"urn:li:share:{share_id}"},
            "commentary": {"commentaryText": {"text": f"Test {share_id}"}},
        },
    }


def scheduled_page(elements: list[dict], start: int, total: int) -> httpx.Response:
    collection = {"paging": {"start": start, "count": 2, "total": total}, "elements": elements}
    return httpx.Response(
        200, json={"data": {"contentcreationDashSharePreviewsByShareLifeCycleState": collection}}
    )


async def test_scheduled_pages_with_a_cursor_tied_to_the_list(api, payloads):
    first = scheduled_page([preview("2001", 1793584800000), preview("2002", 1793671200000)], 0, 3)
    second = scheduled_page([preview("2003", 1793757600000), {"miniUpdate": {}}], 2, 3)
    client, posts, seen = api(first, second)
    async with client:
        page = await posts.scheduled(count=2)
        later = await posts.scheduled(count=2, cursor=page.next)
    assert payloads.params(seen[0])["queryId"] == SCHEDULED.id
    assert payloads.variables(seen[0]) == {
        "shareLifeCycleState": "SCHEDULED",
        "start": "0",
        "count": "2",
    }
    assert payloads.variables(seen[1])["start"] == "2"
    assert [post.share_urn for post in page.items] == ["urn:li:share:2001", "urn:li:share:2002"]
    assert page.items[0].text == "Test 2001"
    assert page.items[0].publish_at is not None
    assert page.items[0].publish_at.timestamp() == 1793584800
    assert page.items[0].description == "Posting Mon, Nov 2 at 7:30 AM"
    assert page.total == 3 and page.has_more
    assert [post.share_urn for post in later.items] == ["urn:li:share:2003"]
    assert later.next is None


async def test_a_stale_total_with_no_elements_ends_the_list(api):
    client, posts, _ = api(scheduled_page([], 0, 1))
    async with client:
        page = await posts.scheduled()
    assert page.items == () and page.next is None


async def test_a_cursor_from_another_list_is_refused(api):
    client, posts, seen = api()
    async with client:
        with pytest.raises(ValueError):
            await posts.scheduled(cursor=Cursor("comments.list", "urn:li:activity:1000", 10))
    assert seen == []


async def test_a_reply_without_the_collection_is_a_protocol_error(api):
    client, posts, _ = api(httpx.Response(200, json={"data": {}}))
    async with client:
        with pytest.raises(ProtocolError):
            await posts.scheduled()
