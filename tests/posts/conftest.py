"""Synthetic share replies and a posts resource over a mock transport."""

import json
from types import SimpleNamespace

import httpx
import pytest
from restli_decode import params
from restli_decode import variables

from async_linkedinlib import LinkedIn
from async_linkedinlib.resources.posts import Posts
from async_linkedinlib.transport.voyager import Voyager

SHARE = "urn:li:share:2000"
ACTIVITY = "urn:li:activity:1000"
PROFILE = "urn:li:fsd_profile:ACoTestProfile"
COMPANY = "urn:li:fsd_company:777"
SOCIAL_DETAIL = f"urn:li:fsd_socialDetail:({ACTIVITY},{ACTIVITY},urn:li:highlightedReply:-)"


def update(text: str = "Synthetic post", share: str = SHARE) -> dict:
    """A published feed `Update` as the share reply embeds it."""
    return {
        "entityUrn": f"urn:li:fsd_update:({ACTIVITY},FEED_DETAIL,EMPTY,DEFAULT,false)",
        "metadata": {"backendUrn": ACTIVITY, "shareUrn": share, "shareAudience": "PUBLIC"},
        "socialDetail": {
            "entityUrn": SOCIAL_DETAIL,
            "threadUrn": ACTIVITY,
            "allowedCommentersScope": "ALL",
            "totalSocialActivityCounts": {"numLikes": 0, "numComments": 0, "numShares": 0},
        },
        "actor": {
            "backendUrn": "urn:li:member:42",
            "name": {"text": "Test Member"},
            "subDescription": {"text": "now • Visible to anyone"},
        },
        "commentary": {"text": {"text": text, "attributesV2": []}},
    }


def share_reply(field: str, published: dict | None, message: str, key: str = SHARE) -> dict:
    """A GraphQL action envelope for a create or update share mutation."""
    if published is None:
        status = {"lifecycleState": None, "feedbackData": {"toastComponent": {"text": message}}}
    else:
        status = {
            "lifecycleState": {"PublishedState": published},
            "feedbackData": {"promptComponentV2": {"promptHeader": {"mainText": message}}},
        }
    share = {"entityUrn": f"urn:li:fsd_share:{SHARE}", "scheduledAt": None, "status": status}
    return {"value": {"data": {field: {"resourceKey": key, "entity": share}}}}


def body(request: httpx.Request) -> dict:
    return json.loads(request.content)


@pytest.fixture
def payloads():
    """The synthetic builders and decoders above, for the test modules."""
    return SimpleNamespace(
        SHARE=SHARE,
        ACTIVITY=ACTIVITY,
        PROFILE=PROFILE,
        COMPANY=COMPANY,
        SOCIAL_DETAIL=SOCIAL_DETAIL,
        update=update,
        share_reply=share_reply,
        body=body,
        params=params,
        variables=variables,
    )


@pytest.fixture
def api(session):
    """Build `(client, Posts, seen requests)`; `replies` answer requests in order."""

    def build(*replies: httpx.Response):
        seen: list[httpx.Request] = []
        queue = list(replies)

        def record(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            assert queue, f"unexpected request {request.method} {request.url.path}"
            return queue.pop(0)

        client = LinkedIn(session, transport=httpx.MockTransport(record))
        return client, Posts(Voyager(client._transport)), seen

    return build
