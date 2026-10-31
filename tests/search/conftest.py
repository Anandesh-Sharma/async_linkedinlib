"""Synthetic Voyager search payloads, a rest.li variables decoder and a mocked Search."""

from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
import pytest
from restli_decode import decode

from async_linkedinlib import LinkedIn
from async_linkedinlib.resources.search import Search
from async_linkedinlib.transport.voyager import Voyager

PROFILE = "urn:li:fsd_profile:ACoTestProfileOne"


def text(value: str) -> dict:
    return {"textDirection": "USER_LOCALE", "text": value, "attributesV2": []}


def person_entity(profile: str = PROFILE, name: str = "Ada Example") -> dict:
    return {
        "entityUrn": f"urn:li:fsd_entityResultViewModel:({profile},SEARCH_SRP,DEFAULT)",
        "trackingUrn": "urn:li:member:1001",
        "template": "UNIVERSAL",
        "title": text(name),
        "primarySubtitle": text("Engineer at Example Co"),
        "secondarySubtitle": text("Testville"),
        "summary": text("Current: Engineer at Example Co"),
        "entityCustomTrackingInfo": {"memberDistance": "DISTANCE_2", "nameMatch": False},
        "badgeIcon": {"attributes": [{"detailData": {"systemImage": "SYS_ICN_VERIFIED_SMALL"}}]},
        "insightsResolutionResults": [{"simpleInsight": {"title": text("3 mutual connections")}}],
        "navigationUrl": "https://www.linkedin.com/in/ada-example?miniProfileUrn=x",
    }


def company_entity(company_id: str = "2001", name: str = "Example Co") -> dict:
    return {
        "entityUrn": f"urn:li:fsd_entityResultViewModel:(urn:li:fsd_company:{company_id},"
        "SEARCH_SRP,DEFAULT)",
        "trackingUrn": f"urn:li:company:{company_id}",
        "title": text(name),
        "primarySubtitle": text("Software Development • Testville"),
        "secondarySubtitle": text("1K followers"),
        "summary": text("Synthetic company summary"),
        "navigationUrl": "https://www.linkedin.com/company/example-co/?trk=x",
    }


def update(activity: str = "urn:li:activity:3001", author: str = "urn:li:member:1001") -> dict:
    return {
        "metadata": {"backendUrn": activity, "shareAudience": "PUBLIC"},
        "socialDetail": {"threadUrn": activity, "totalSocialActivityCounts": {"numLikes": 4}},
        "actor": {
            "backendUrn": author,
            "name": text("Ada Example"),
            "description": text("Engineer"),
            "subDescription": text("2h • Edited"),
        },
        "commentary": {"text": text("Synthetic post")},
        "content": {"imageComponent": {"images": []}},
    }


def clusters(
    *groups: list[dict],
    start: int = 0,
    count: int = 10,
    total: int = 100,
    results: int | None = 12345,
    token: str | None = None,
    titles: tuple[str | None, ...] = (),
) -> dict:
    """A `searchDashClustersByAll` collection; each group is a list of item unions."""
    elements = [
        {
            "position": index + 1,
            "title": text(titles[index]) if index < len(titles) and titles[index] else None,
            "items": [{"item": item, "position": n} for n, item in enumerate(group)],
        }
        for index, group in enumerate(groups)
    ]
    return {
        "data": {
            "searchDashClustersByAll": {
                "metadata": {
                    "totalResultCount": results,
                    "paginationToken": token,
                    "primaryResultType": "PEOPLE",
                },
                "paging": {"start": start, "count": count, "total": total},
                "elements": elements,
            }
        }
    }


def sent(request: httpx.Request) -> SimpleNamespace:
    """The query ID, operation name and decoded variables of a GraphQL GET."""
    query = request.url.query.decode()
    params = {key: values[0] for key, values in parse_qs(query).items()}
    raw = next((part for part in query.split("&") if part.startswith("variables=")), "")
    return SimpleNamespace(
        query_id=params["queryId"],
        name=params["queryName"],
        variables=decode(raw.removeprefix("variables=")) if raw else {},
    )


@pytest.fixture
def payloads():
    """The synthetic builders and decoders above, for the test modules."""
    return SimpleNamespace(
        PROFILE=PROFILE,
        text=text,
        person_entity=person_entity,
        company_entity=company_entity,
        update=update,
        clusters=clusters,
        sent=sent,
    )


@pytest.fixture
def api(session):
    """Build `(client, Search, seen requests)` answering each request with the next reply.

    A reply is a JSON body, raw bytes, or a `(status, body)` pair.
    """

    def build(*replies):
        queue = list(replies)
        seen: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            reply = queue.pop(0)
            status, body = reply if isinstance(reply, tuple) else (200, reply)
            if isinstance(body, bytes):
                return httpx.Response(status, content=body)
            return httpx.Response(status, json=body)

        client = LinkedIn(session, transport=httpx.MockTransport(handle))
        return client, Search(Voyager(client._transport)), seen

    return build
