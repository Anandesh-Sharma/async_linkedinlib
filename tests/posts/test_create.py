from datetime import UTC
from datetime import datetime
from datetime import timedelta

import httpx
import pytest

from async_linkedinlib.exceptions import OperationRejected
from async_linkedinlib.exceptions import ProtocolError
from async_linkedinlib.models.comments import Mention
from async_linkedinlib.models.posts import CommentScope
from async_linkedinlib.models.posts import Visibility
from async_linkedinlib.resources.posts.resource import CREATE
from async_linkedinlib.resources.posts.resource import DELETE
from async_linkedinlib.resources.posts.resource import UPDATE

CREATED = "createContentcreationDashShares"
UPDATED = "updateContentcreationDashShares"


def reply(data: dict) -> httpx.Response:
    return httpx.Response(200, json=data)


async def test_create_sends_the_share_box_mutation_and_reads_the_published_post(api, payloads):
    text = "Test 🧪 hello Test Member and Test Co"
    published = payloads.update(text)
    created = payloads.share_reply(
        CREATED, published, "Post successful.", key=f"urn:li:fsd_share:{payloads.SHARE}"
    )
    client, posts, seen = api(reply(created))
    async with client:
        shared = await posts.create(
            text,
            visibility=Visibility.CONNECTIONS_ONLY,
            comments=CommentScope.NOBODY,
            mentions=[
                Mention(payloads.COMPANY, text.index("Test Co"), 7),
                Mention(payloads.PROFILE, text.index("Test Member"), 11),
            ],
        )
    request = seen[0]
    assert request.method == "POST"
    assert request.url.path == "/voyager/api/graphql"
    assert payloads.params(request)["queryId"] == CREATE.id
    assert request.headers["x-li-graphql-pegasus-client"] == "true"
    assert payloads.body(request) == {
        "queryId": CREATE.id,
        "queryName": "ContentCreationShares",
        "variables": {
            "entity": {
                "allowedCommentersScope": "NONE",
                "origin": "FEED",
                "visibilityDataUnion": {"visibilityType": "CONNECTIONS_ONLY"},
                "commentary": {
                    "text": text,
                    "attributesV2": [
                        # Code points: the emoji counts as one, as the server counts.
                        {
                            "start": 13,
                            "length": 11,
                            "detailDataUnion": {"profileFullName": payloads.PROFILE},
                        },
                        {
                            "start": 29,
                            "length": 7,
                            "detailDataUnion": {"companyName": payloads.COMPANY},
                        },
                    ],
                },
            }
        },
    }
    assert shared.share_urn == payloads.SHARE
    assert shared.activity_urn == payloads.ACTIVITY
    assert shared.published is True
    assert shared.social_detail_urn == payloads.SOCIAL_DETAIL
    assert shared.message == "Post successful."
    assert shared.post is not None and shared.post.text == text


async def test_scheduled_create_sends_the_time_and_reads_an_unpublished_share(api, payloads):
    when = datetime.now(UTC).replace(microsecond=0) + timedelta(days=2)
    client, posts, seen = api(reply(payloads.share_reply(CREATED, None, "Post scheduled.")))
    async with client:
        shared = await posts.create("Test later", publish_at=when)
    entity = payloads.body(seen[0])["variables"]["entity"]
    assert entity["scheduledAt"] == int(when.timestamp()) * 1000
    assert entity["intendedShareLifeCycleState"] == "SCHEDULED"
    assert entity["allowedCommentersScope"] == "ALL"
    assert entity["visibilityDataUnion"] == {"visibilityType": "ANYONE"}
    assert shared.share_urn == payloads.SHARE
    assert shared.published is False
    assert shared.activity_urn is None and shared.post is None
    assert shared.message == "Post scheduled."


@pytest.mark.parametrize(
    "call",
    [
        lambda p: p.create(""),
        lambda p: p.create("   "),
        lambda p: p.create("Test", publish_at=datetime(2030, 1, 1)),
        lambda p: p.create("Test", publish_at=datetime.now(UTC) - timedelta(minutes=1)),
        lambda p: p.create("Test", visibility="EVERYONE"),
        lambda p: p.create("Test", comments="SOME"),
        lambda p: p.create("Test", mentions=[Mention("urn:li:member:42", 0, 4)]),
        lambda p: p.create("Test", mentions=[Mention("urn:li:fsd_profile:A", 0, 5)]),
        lambda p: p.create("Test", mentions=[Mention("urn:li:fsd_profile:A", 0, 0)]),
        lambda p: p.create(
            "Test x",
            mentions=[Mention("urn:li:fsd_profile:A", 0, 4), Mention("urn:li:fsd_profile:B", 2, 3)],
        ),
        lambda p: p.create("Test", mentions=["urn:li:fsd_profile:A"]),
        lambda p: p.create("Test", mentions=Mention("urn:li:fsd_profile:A", 0, 4)),
        lambda p: p.create("Test", media="photo.png"),
        lambda p: p.create("Test", media=[]),
    ],
)
async def test_invalid_posts_are_refused_before_any_request(api, call):
    client, posts, seen = api()
    async with client:
        with pytest.raises(ValueError):
            await call(posts)
    assert seen == []


async def test_a_refused_post_raises_with_the_server_reason(api):
    limit = "You've reached today's posting limit."
    client, posts, _ = api(reply({"value": {"errors": [{"message": limit}]}}))
    async with client:
        with pytest.raises(OperationRejected) as caught:
            await posts.create("Test")
    assert caught.value.reasons == (limit,)


async def test_a_reply_without_a_share_is_a_protocol_error(api):
    client, posts, _ = api(reply({"value": {"data": {CREATED: {"entity": {}}}}}))
    async with client:
        with pytest.raises(ProtocolError):
            await posts.create("Test")


async def test_edit_replaces_only_the_text_and_mentions(api, payloads):
    text = "Test edited Test Member"
    client, posts, seen = api(reply(payloads.share_reply(UPDATED, payloads.update(text), "Done")))
    async with client:
        shared = await posts.edit(
            payloads.SHARE, text, mentions=[Mention(payloads.PROFILE, 12, 11)]
        )
    assert payloads.body(seen[0]) == {
        "queryId": UPDATE.id,
        "queryName": "UpdateContentCreationShares",
        "variables": {
            "entity": {
                "resourceKey": payloads.SHARE,
                "entity": {
                    "commentary": {
                        "text": text,
                        "attributesV2": [
                            {
                                "start": 12,
                                "length": 11,
                                "detailDataUnion": {"profileFullName": payloads.PROFILE},
                            }
                        ],
                    }
                },
            }
        },
    }
    assert shared.post is not None and shared.post.text == text


@pytest.mark.parametrize(
    "call",
    [
        lambda p: p.edit("urn:li:share:2000", ""),
        lambda p: p.edit("urn:li:activity:1000", "Test"),
        lambda p: p.delete("urn:li:share:abc"),
        lambda p: p.cancel_scheduled("share:2000"),
        lambda p: p.reschedule("urn:li:share:2000", datetime(2030, 1, 1)),
        lambda p: p.repost_with_thoughts("urn:li:share:2000", " "),
        lambda p: p.repost_with_thoughts("urn:li:activity:1000", "Test"),
    ],
)
async def test_invalid_management_calls_send_nothing(api, call):
    client, posts, seen = api()
    async with client:
        with pytest.raises(ValueError):
            await call(posts)
    assert seen == []


async def test_delete_and_cancel_address_the_share(api, payloads):
    deleted = {
        "value": {"data": {"deleteContentcreationDashShares": {"resourceKey": payloads.SHARE}}}
    }
    client, posts, seen = api(reply(deleted), reply(deleted))
    async with client:
        assert await posts.delete(payloads.SHARE) is None
        assert await posts.cancel_scheduled("urn:li:ugcPost:3000") is None
    first, second = (payloads.body(request) for request in seen)
    assert first["queryId"] == DELETE.id
    assert first["queryName"] == "DeleteContentcreationSharesByUrn"
    assert first["variables"] == {"resourceKey": payloads.SHARE}
    assert second["variables"] == {
        "resourceKey": "urn:li:ugcPost:3000",
        "shareLifecycleState": "SCHEDULED",
    }


async def test_reschedule_sends_only_the_new_time(api, payloads):
    when = datetime.now(UTC).replace(microsecond=0) + timedelta(days=3)
    client, posts, seen = api(reply(payloads.share_reply(UPDATED, None, "Post scheduled.")))
    async with client:
        shared = await posts.reschedule(payloads.SHARE, when)
    assert payloads.body(seen[0])["variables"] == {
        "entity": {
            "resourceKey": payloads.SHARE,
            "entity": {"scheduledAt": int(when.timestamp()) * 1000},
        }
    }
    assert shared.published is False


async def test_repost_with_thoughts_references_the_original_share(api, payloads):
    client, posts, seen = api(reply(payloads.share_reply(CREATED, payloads.update(), "Done")))
    async with client:
        await posts.repost_with_thoughts("urn:li:ugcPost:3000", "Test thoughts")
    entity = payloads.body(seen[0])["variables"]["entity"]
    assert entity["origin"] == "RESHARE"
    assert entity["parentUrn"] == "urn:li:ugcPost:3000"
    assert entity["commentary"] == {"text": "Test thoughts", "attributesV2": []}
    assert "media" not in entity
