import json
from dataclasses import replace

import httpx
import pytest

from async_linkedinlib import ProtocolError
from async_linkedinlib import ReactionType
from async_linkedinlib.exceptions import OperationRejected
from async_linkedinlib.models.comments import Comment
from async_linkedinlib.models.comments import Mention
from async_linkedinlib.resources import reactions
from async_linkedinlib.resources.comments.resource import CREATE
from async_linkedinlib.resources.comments.resource import HIDE
from async_linkedinlib.resources.comments.resource import UNHIDE

DECORATION = "com.linkedin.voyager.dash.deco.social.NormComment-38"


def created(comment):
    body = {"value": {"data": {"createSocialDashNormComments": {"entity": {"comment": comment}}}}}
    return lambda request: httpx.Response(200, json=body)


def mutation(request):
    return json.loads(request.content)


async def test_create_posts_the_app_mutation_with_mentions(api, payloads):
    client, comments, seen = api(created(payloads.make_comment("2001", "Test hello")))
    async with client:
        comment = await comments.create(
            payloads.POST, "Test hello", mentions=[Mention(payloads.PROFILE, 0, 4)]
        )
    request = seen[0]
    assert request.method == "POST"
    assert request.url.path == "/voyager/api/graphql"
    assert payloads.graphql_params(request)["action"] == "execute"
    assert mutation(request) == {
        "queryId": CREATE.id,
        "queryName": "CreateComment",
        "variables": {
            "entity": {
                "commentary": {
                    "text": "Test hello",
                    "attributesV2": [
                        {
                            "start": 0,
                            "length": 4,
                            "detailDataUnion": {"profileFullName": payloads.PROFILE},
                        }
                    ],
                    "textDirection": "FIRST_STRONG",
                },
                "threadUrn": payloads.POST,
            }
        },
    }
    assert comment.urn == payloads.comment_urn("2001")
    assert comment.text == "Test hello"


async def test_reply_uses_the_parent_comment_as_thread(api, payloads):
    client, comments, seen = api(created(payloads.make_comment("2002", parent="2001")))
    async with client:
        reply = await comments.reply(payloads.entity_urn("2001"), "Plain reply")
    entity = mutation(seen[0])["variables"]["entity"]
    assert entity["threadUrn"] == payloads.comment_urn("2001")
    assert entity["commentary"] == {
        "text": "Plain reply",
        "attributesV2": [],
        "textDirection": "FIRST_STRONG",
    }
    assert reply.parent_urn == payloads.comment_urn("2001")


async def test_edit_patches_the_norm_comment_entity(api, payloads):
    edited = payloads.make_comment("2001", "New text")
    edited["edited"] = True
    body = {"entityUrn": "x", "singleComment": {"elements": [edited]}}
    client, comments, seen = api(lambda request: httpx.Response(200, json=body))
    async with client:
        comment = await comments.edit(payloads.comment_urn("2001"), "New text")
    request = seen[0]
    assert request.method == "POST"
    assert request.url.raw_path.decode() == (
        "/voyager/api/voyagerSocialDashNormComments/"
        f"{payloads.entity_urn('2001')}?decorationId={DECORATION}"
    )
    assert json.loads(request.content) == {
        "patch": {
            "$set": {
                "commentary": {
                    "text": "New text",
                    "attributesV2": [],
                    "textDirection": "FIRST_STRONG",
                }
            }
        }
    }
    assert comment.text == "New text"
    assert comment.edited is True


async def test_delete_removes_the_norm_comment_entity(api, payloads):
    client, comments, seen = api(lambda request: httpx.Response(204))
    async with client:
        assert await comments.delete(payloads.comment_urn("2001")) is None
    assert seen[0].method == "DELETE"
    assert seen[0].url.raw_path.decode() == (
        f"/voyager/api/voyagerSocialDashNormComments/{payloads.entity_urn('2001')}"
    )


async def test_reactions_address_the_comment_thread(api, payloads):
    ok = {"value": {"data": {"result": {}}}}
    client, comments, seen = api(lambda request: httpx.Response(200, json=ok))
    thread = payloads.comment_urn("2001")
    async with client:
        await comments.react(payloads.entity_urn("2001"))
        await comments.change_reaction(thread, ReactionType.FUNNY)
        await comments.unreact(thread)
    sent = [mutation(request) for request in seen]
    assert [body["queryId"] for body in sent] == [
        reactions.CREATE.id,
        reactions.UPDATE.id,
        reactions.DELETE.id,
    ]
    assert sent[0]["variables"] == {"threadUrn": thread, "entity": {"reactionType": "LIKE"}}
    assert sent[1]["variables"] == {"threadUrn": thread, "newReactionType": "ENTERTAINMENT"}
    assert sent[2]["variables"] == {"threadUrn": thread}


async def test_hide_and_unhide_send_the_offered_hide_action(api, payloads):
    ok = {"value": {"data": {"doHideSocialDashHideCommentAction": {}}}}
    client, comments, seen = api(lambda request: httpx.Response(200, json=ok))
    comment = Comment.from_json(payloads.make_comment("2001"))
    assert comment is not None
    offered = replace(comment, hide_action_urn="urn:li:fsd_hideCommentAction:test")
    async with client:
        await comments.hide(offered)
        await comments.unhide(offered)
        with pytest.raises(ValueError):
            await comments.hide(comment)
    assert [mutation(request)["queryId"] for request in seen] == [HIDE.id, UNHIDE.id]
    assert mutation(seen[0])["variables"] == {
        "hideCommentActionUrn": "urn:li:fsd_hideCommentAction:test"
    }


async def test_rejected_create_raises_operation_rejected(api, payloads):
    body = {"value": {"errors": [{"message": "Commenting is disabled"}]}}
    client, comments, _ = api(lambda request: httpx.Response(200, json=body))
    async with client:
        with pytest.raises(OperationRejected) as caught:
            await comments.create(payloads.POST, "Test hello")
    assert caught.value.reasons == ("Commenting is disabled",)


@pytest.mark.parametrize(
    "body",
    [
        {"value": {"data": {"createSocialDashNormComments": {"entity": {}}}}},
        {"value": {"data": {"createSocialDashNormComments": {"entity": {"comment": {"x": 1}}}}}},
    ],
)
async def test_create_reply_without_the_comment_raises_protocol_error(api, payloads, body):
    client, comments, _ = api(lambda request: httpx.Response(200, json=body))
    async with client:
        with pytest.raises(ProtocolError):
            await comments.create(payloads.POST, "Test hello")


async def test_edit_reply_without_the_comment_raises_protocol_error(api, payloads):
    client, comments, _ = api(lambda request: httpx.Response(200, json={"singleComment": {}}))
    async with client:
        with pytest.raises(ProtocolError):
            await comments.edit(payloads.comment_urn("2001"), "New text")


PROFILE = "urn:li:fsd_profile:ACoTestProfile"


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.create("urn:li:activity:1000", "   "),
        lambda c: c.create("urn:li:activity:1000", 5),
        lambda c: c.create("not-a-urn", "Test hello"),
        lambda c: c.create("urn:li:activity:1000", "Test", mentions=[Mention(PROFILE, 2, 3)]),
        lambda c: c.create("urn:li:activity:1000", "Test", mentions=[Mention(PROFILE, 0, 0)]),
        lambda c: c.create("urn:li:activity:1000", "Test", mentions=[Mention(PROFILE, -1, 2)]),
        lambda c: c.create(
            "urn:li:activity:1000", "Test", mentions=[Mention("urn:li:member:1", 0, 4)]
        ),
        lambda c: c.create("urn:li:activity:1000", "Test", mentions=Mention(PROFILE, 0, 4)),
        lambda c: c.reply("urn:li:activity:1000", "Test hello"),
        lambda c: c.edit("urn:li:comment:(activity:1000,abc)", "Test hello"),
        lambda c: c.delete("urn:li:fsd_comment:(2001,activity:1000)"),
        lambda c: c.react("urn:li:comment:(activity:1000,2001)", "WOW"),
        lambda c: c.hide("urn:li:comment:(activity:1000,2001)"),
    ],
)
async def test_bad_write_input_raises_value_error_without_a_request(api, call):
    client, comments, seen = api(lambda request: httpx.Response(500))
    async with client:
        with pytest.raises(ValueError):
            await call(comments)
    assert seen == []
