"""Synthetic Voyager comment payloads and a comments resource over a mock transport."""

from types import SimpleNamespace

import httpx
import pytest
from restli_decode import params as graphql_params
from restli_decode import variables

from async_linkedinlib import LinkedIn
from async_linkedinlib.resources.comments import Comments
from async_linkedinlib.transport.voyager import Voyager

POST = "urn:li:activity:1000"
PROFILE = "urn:li:fsd_profile:ACoTestProfile"


def comment_urn(comment_id: str) -> str:
    return f"urn:li:comment:(activity:1000,{comment_id})"


def entity_urn(comment_id: str) -> str:
    return f"urn:li:fsd_comment:({comment_id},urn:li:activity:1000)"


def make_comment(
    comment_id: str = "2001",
    text: str = "Synthetic comment",
    *,
    parent: str | None = None,
    replies: tuple[dict, ...] = (),
    reacted: str | None = None,
) -> dict:
    urn = comment_urn(comment_id)
    return {
        "urn": urn,
        "entityUrn": entity_urn(comment_id),
        "parentCommentBackendUrn": comment_urn(parent) if parent else None,
        "createdAt": 1700000000000,
        "edited": False,
        "pinned": False,
        "permalink": f"https://www.linkedin.com/feed/update/{POST}?commentUrn=x",
        "actions": ["SHARE_VIA", "EDIT_COMMENT", "DELETE"],
        "hideCommentAction": None,
        "commentary": {
            "text": text,
            "attributesV2": [
                {"start": 0, "length": 4, "detailData": {"profileMention": {"entityUrn": PROFILE}}}
            ],
        },
        "commenter": {
            "urn": "urn:li:member:42",
            "author": True,
            "title": {"text": "Test Member"},
            "subtitle": "Fixture headline",
            "navigationUrl": "https://www.linkedin.com/in/test-member?trk=x",
            "actor": {"profileUrn": {"entityUrn": PROFILE}},
        },
        "socialDetail": {
            "threadUrn": urn,
            "socialPermissions": {"canPostComments": True, "canReact": True},
            "totalSocialActivityCounts": {
                "numLikes": 2,
                "numComments": len(replies),
                "liked": reacted is not None,
                "reacted": reacted,
                "reactionTypeCounts": [{"reactionType": "LIKE", "count": 2}],
            },
            "comments": {
                "paging": {"start": 0, "count": 1, "total": len(replies)},
                "elements": list(replies),
            },
        },
    }


def collection(elements: list[dict], *, start: int, total: int, token: str | None = None) -> dict:
    return {
        "metadata": {"paginationToken": token},
        "paging": {"start": start, "count": len(elements), "total": total},
        "elements": elements,
    }


@pytest.fixture
def payloads():
    """The synthetic builders and decoders above, for the test modules."""
    return SimpleNamespace(
        POST=POST,
        PROFILE=PROFILE,
        comment_urn=comment_urn,
        entity_urn=entity_urn,
        make_comment=make_comment,
        collection=collection,
        variables=variables,
        graphql_params=graphql_params,
    )


@pytest.fixture
def api(session):
    """Build `(client, Comments, seen requests)` answering with `handle(request)`."""

    def build(handle):
        seen: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handle(request)

        client = LinkedIn(session, transport=httpx.MockTransport(record))
        return client, Comments(Voyager(client._transport)), seen

    return build
