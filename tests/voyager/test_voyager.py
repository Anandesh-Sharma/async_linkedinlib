import json
from urllib.parse import parse_qs
from urllib.parse import unquote
from urllib.parse import urlsplit

import httpx
import pytest

from async_linkedinlib import HTTPError
from async_linkedinlib import LinkedIn
from async_linkedinlib import ProtocolError
from async_linkedinlib import ReactionType
from async_linkedinlib import UnconfirmedWrite
from async_linkedinlib.exceptions import OperationRejected
from async_linkedinlib.resources.reactions import Reactions
from async_linkedinlib.transport import Transport
from async_linkedinlib.transport.voyager import GraphQLQuery
from async_linkedinlib.transport.voyager import Voyager

QUERY = GraphQLQuery("voyagerFeedDashExample.0123456789abcdef0123456789abcdef", "Example")


def voyager(session, handle):
    client = LinkedIn(session, transport=httpx.MockTransport(handle))
    return client, Voyager(client._transport)


async def test_query_sends_restli_variables_and_returns_data(session):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"data": {"result": {"ok": True}}})

    client, api = voyager(session, handle)
    async with client:
        data = await api.query(QUERY, {"start": 0, "urn": "urn:li:activity:1"})
    request = seen[0]
    assert request.method == "GET"
    assert request.url.path == "/voyager/api/graphql"
    raw = request.url.query.decode()
    assert "variables=(start:0,urn:urn%3Ali%3Aactivity%3A1)" in raw
    params = parse_qs(raw)
    assert params["queryId"] == [QUERY.id]
    assert params["queryName"] == ["Example"]
    assert request.headers["accept"] == "application/json"
    assert request.headers["x-li-graphql-pegasus-client"] == "true"
    assert request.headers["csrf-token"] == "ajax:1234567890123456789"
    assert data == {"result": {"ok": True}}


async def test_mutation_posts_json_and_unwraps_the_action_value(session):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"value": {"data": {"done": {"result": "x"}}}})

    client, api = voyager(session, handle)
    async with client:
        data = await api.mutate(QUERY, {"threadUrn": "urn:li:activity:1"})
    request = seen[0]
    assert request.method == "POST"
    assert parse_qs(request.url.query.decode())["action"] == ["execute"]
    assert json.loads(request.content) == {
        "queryId": QUERY.id,
        "queryName": "Example",
        "variables": {"threadUrn": "urn:li:activity:1"},
    }
    assert data == {"done": {"result": "x"}}


@pytest.mark.parametrize(
    "body",
    [
        {"errors": [{"message": "Variable 'x' has an invalid value"}]},
        {"value": {"errors": [{"message": "Variable 'x' has an invalid value"}]}},
    ],
)
async def test_graphql_errors_raise_operation_rejected(session, body):
    client, api = voyager(session, lambda request: httpx.Response(200, json=body))
    async with client:
        with pytest.raises(OperationRejected) as caught:
            if "value" in body:
                await api.mutate(QUERY, {})
            else:
                await api.query(QUERY)
    assert caught.value.reasons == ("Variable 'x' has an invalid value",)


async def test_missing_data_is_a_protocol_error(session):
    client, api = voyager(session, lambda request: httpx.Response(200, json={"other": 1}))
    async with client:
        with pytest.raises(ProtocolError):
            await api.query(QUERY)


async def test_rest_post_returns_reply_and_created_id(session):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(201, headers={"x-restli-id": "urn:li:x:9"})

    client, api = voyager(session, handle)
    async with client:
        reply = await api.post("voyagerExampleThings", {"a": 1}, {"action": "create"})
    assert seen[0].url.path == "/voyager/api/voyagerExampleThings"
    assert seen[0].url.query.decode() == "action=create"
    assert json.loads(seen[0].content) == {"a": 1}
    assert reply.data == {}
    assert reply.created_id == "urn:li:x:9"


async def test_rest_client_errors_keep_only_the_one_line_reason(session):
    def handle(request):
        return httpx.Response(422, json={"message": "Comment text too long", "status": 422})

    client, api = voyager(session, handle)
    async with client:
        with pytest.raises(HTTPError) as caught:
            await api.get("voyagerExampleThings/1")
    assert caught.value.status_code == 422
    assert caught.value.reason == "Comment text too long"


def test_resource_names_and_query_ids_are_validated(session):
    with pytest.raises(ValueError):
        GraphQLQuery("feed.123", "Example")
    with pytest.raises(ValueError):
        GraphQLQuery(QUERY.id, "bad name")


async def test_resource_paths_cannot_escape_the_voyager_api(session):
    client, api = voyager(session, lambda request: httpx.Response(200, json={}))
    async with client:
        for resource in ("../mob/sso/you", "voyagerX?y=1", "voyagerX#a", "http://x"):
            with pytest.raises(ValueError):
                await api.get(resource)


async def test_reactions_send_the_app_mutations(session):
    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"value": {"data": {}}})

    client, api = voyager(session, handle)
    reactions = Reactions(api)
    async with client:
        await reactions.add("urn:li:activity:1", ReactionType.CELEBRATE)
        await reactions.change("urn:li:activity:1", ReactionType.LOVE)
        await reactions.remove("urn:li:activity:1")
        with pytest.raises(ValueError):
            await reactions.add("activity:1")
    assert [body["queryName"] for body in seen] == [
        "CreateSocialDashReaction",
        "UpdateSocialDashReaction",
        "DeleteSocialDashReaction",
    ]
    assert seen[0]["variables"] == {
        "threadUrn": "urn:li:activity:1",
        "entity": {"reactionType": "PRAISE"},
    }
    assert seen[1]["variables"]["newReactionType"] == "EMPATHY"
    assert unquote(seen[2]["variables"]["threadUrn"]) == "urn:li:activity:1"


async def test_raw_upload_bodies_reach_the_wire(session):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(201)

    client = LinkedIn(session, transport=httpx.MockTransport(handle))
    async with client:
        await client._transport.request(
            "PUT", "/dms-uploads/x", content=b"\x00\x01", headers={"content-type": "image/png"}
        )
        with pytest.raises(ValueError):
            await client._transport.request("POST", "/x", json={}, content=b"x")
    assert seen[0].content == b"\x00\x01"
    assert seen[0].headers["content-type"] == "image/png"
    assert urlsplit(str(seen[0].url)).netloc == "www.linkedin.com"


async def test_null_field_errors_are_accepted_only_when_asked(session):
    null = {"message": "null", "extensions": {"classification": "NullValueInNonNullableField"}}
    other = {"message": "boom", "extensions": {"classification": "DataFetchingException"}}

    def handle(request):
        errors = [null, other] if "other" in str(request.url) else [null]
        return httpx.Response(200, json={"data": {"x": {"a": 1}}, "errors": errors})

    client, api = voyager(session, handle)
    async with client:
        with pytest.raises(OperationRejected):
            await api.query(QUERY, {"k": "v"})
        assert await api.query(QUERY, {"k": "v"}, ignore_null_field_errors=True) == {"x": {"a": 1}}
        with pytest.raises(OperationRejected):
            await api.query(QUERY, {"k": "other"}, ignore_null_field_errors=True)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/dms-uploads/../voyager/api/x",
        "https://www.linkedin.com/dms-uploads/%2e%2e/voyager/api/x",
        "https://www.linkedin.com/dms-uploads/./x",
        "http://www.linkedin.com/dms-uploads/x",
        "https://www.linkedin.com.evil.test/dms-uploads/x",
        "https://user@www.linkedin.com/dms-uploads/x",
        "https://www.linkedin.com/ambry/x",
        None,
    ],
)
def test_upload_paths_outside_the_offered_prefix_are_refused(url):
    assert Transport.upload_path(url, "/dms-uploads/") is None


def test_upload_path_keeps_the_query():
    url = "https://www.linkedin.com/dms-uploads/abc/upload?ca=v&cn=x"
    assert Transport.upload_path(url, "/dms-uploads/") == "/dms-uploads/abc/upload?ca=v&cn=x"


@pytest.mark.parametrize(
    "urn",
    ["urn:li:member:1", "urn:li:fsd_update:(urn:li:activity:1,MAIN_FEED)", "urn:li:share:1"],
)
async def test_reactions_and_comment_lists_refuse_non_thread_urns(session, urn):
    seen = []
    client = LinkedIn(session, transport=httpx.MockTransport(lambda r: seen.append(r)))
    async with client:
        with pytest.raises(ValueError):
            await client.feed.react(urn)
        with pytest.raises(ValueError):
            await client.comments.list(urn)
    assert seen == []


def test_mentions_are_checked_once_for_posts_and_comments():
    from async_linkedinlib import Mention
    from async_linkedinlib.resources.mentions import attributes

    member = Mention("urn:li:fsd_profile:ACoA1", 0, 3)
    company = Mention("urn:li:fsd_company:9", 4, 3)
    written = attributes("Ada Inc", [company, member])
    assert [item["detailDataUnion"] for item in written] == [
        {"profileFullName": "urn:li:fsd_profile:ACoA1"},
        {"companyName": "urn:li:fsd_company:9"},
    ]
    with pytest.raises(ValueError):
        attributes("Ada Inc", [company], companies=False)
    with pytest.raises(ValueError):
        attributes("Ada Inc", [member, Mention("urn:li:fsd_profile:ACoA2", 2, 2)])
    with pytest.raises(ValueError):
        attributes("Ada", (m for m in [member]))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        attributes("Ada", [Mention(5, 0, 1)])  # type: ignore[arg-type]


async def test_accepted_writes_with_unreadable_replies_say_so(session):
    reply = httpx.Response(200, json={"value": {"data": {}}})
    client = LinkedIn(session, transport=httpx.MockTransport(lambda request: reply))
    async with client:
        with pytest.raises(UnconfirmedWrite):
            await client.feed.save("urn:li:activity:1")
        with pytest.raises(UnconfirmedWrite):
            await client.comments.create("urn:li:activity:1", "hello")
