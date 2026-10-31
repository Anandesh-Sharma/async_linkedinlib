"""Synthetic Voyager feed payloads, a rest.li decoder and a feed resource over a mock transport."""

import json
from types import SimpleNamespace

import httpx
import pytest
from restli_decode import params
from restli_decode import variables

from async_linkedinlib import LinkedIn
from async_linkedinlib.resources.feed import Feed
from async_linkedinlib.transport.voyager import Voyager

PROFILE = "urn:li:fsd_profile:ACoTestProfile"


def make_update(
    activity: str = "1000",
    *,
    thread: str | None = None,
    text: str | None = "Synthetic post",
    header: str | None = None,
    reacted: str | None = None,
    content: dict | None = None,
    actor: bool = True,
) -> dict:
    """A dash feed `Update` for activity `urn:li:activity:<activity>`."""
    backend = f"urn:li:activity:{activity}"
    update: dict = {
        "entityUrn": f"urn:li:fsd_update:({backend},MAIN_FEED,EMPTY,DEFAULT,false)",
        "metadata": {
            "backendUrn": backend,
            "shareUrn": "urn:li:share:2000",
            "shareAudience": "PUBLIC",
        },
        "header": {"text": {"text": header}} if header else None,
        "commentary": {"text": {"text": text}} if text else None,
        "content": content or {"imageComponent": {"images": []}},
        "socialContent": {
            "shareUrl": f"https://www.linkedin.com/posts/test_activity-{activity}-x?rcm=ACoViewer"
        },
        "socialDetail": {
            "threadUrn": thread or backend,
            "socialPermissions": {"canReact": True, "canPostComments": True, "canShare": False},
            "totalSocialActivityCounts": {
                "numLikes": 3,
                "numComments": 1,
                "numShares": 0,
                "liked": reacted is not None,
                "reacted": reacted,
                "reactionTypeCounts": [{"reactionType": "LIKE", "count": 3}],
            },
        },
    }
    if actor:
        update["actor"] = actor_block()
    return update


def actor_block(name: str = "Test Member") -> dict:
    return {
        "backendUrn": "urn:li:member:42",
        "name": {
            "text": name,
            "attributesV2": [{"detailData": {"profileFullName": {"entityUrn": PROFILE}}}],
        },
        "description": {"text": "Fixture headline"},
        "subDescription": {"text": "2h • Edited"},
        "navigationContext": {"actionTarget": "https://www.linkedin.com/in/test-member?trk=x"},
    }


def module(index: int = 1) -> dict:
    """A recommendation module: an update without an actor or social thread."""
    return {
        "entityUrn": f"urn:li:fsd_update:(urn:li:aggregate:(urn:li:member:{index}),MAIN_FEED)",
        "metadata": None,
        "aggregatedContent": {"items": []},
    }


def collection(
    elements: list[dict],
    *,
    start: int = 0,
    count: int | None = None,
    total: int | None = None,
    token: str | None = "page-token",
) -> dict:
    paging: dict = {"start": start, "count": len(elements) if count is None else count}
    if total is not None:
        paging["total"] = total
    return {"metadata": {"paginationToken": token}, "paging": paging, "elements": elements}


def graphql(field: str, found: dict | None) -> httpx.Response:
    return httpx.Response(200, json={"data": {field: found}})


def action(field: str, result: object = None) -> httpx.Response:
    data = {field: {"result": result}}
    return httpx.Response(200, json={"value": {"data": data}})


def body(request: httpx.Request) -> dict:
    return json.loads(request.content)


@pytest.fixture
def fx():
    """The synthetic builders and decoders above, for the test modules."""
    return SimpleNamespace(
        PROFILE=PROFILE,
        make_update=make_update,
        actor_block=actor_block,
        module=module,
        collection=collection,
        graphql=graphql,
        action=action,
        params=params,
        variables=variables,
        body=body,
    )


@pytest.fixture
def api(session):
    """Build `(client, Feed, seen requests)` answering with `handle(request)`."""

    def build(handle):
        seen: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handle(request)

        client = LinkedIn(session, transport=httpx.MockTransport(record))
        return client, Feed(Voyager(client._transport)), seen

    return build
