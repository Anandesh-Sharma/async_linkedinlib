"""The Voyager JSON API: persisted GraphQL operations and rest.li resources.

The Android app ships these operations and asks for protobuf; the same routes answer plain
JSON when asked, so requests carry `accept: application/json` and JSON bodies.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..exceptions import OperationRejected
from ..exceptions import ProtocolError
from . import restli
from .http import Transport

_JSON = {"accept": "application/json"}
_GRAPHQL = {"accept": "application/json", "x-li-graphql-pegasus-client": "true"}


@dataclass(frozen=True, slots=True)
class GraphQLQuery:
    """One persisted GraphQL operation from the app: query ID plus operation name."""

    id: str
    name: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"voyager[A-Za-z]+\.[0-9a-f]{32}", self.id):
            raise ValueError("GraphQL query IDs look like voyagerName.<32 hex digits>.")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", self.name):
            raise ValueError("GraphQL operation names are identifiers.")


@dataclass(frozen=True, slots=True)
class Reply:
    """A rest.li reply: its JSON object (empty when none) and the created entity's ID."""

    data: dict[str, Any]
    created_id: str | None = None


class Voyager:
    """Voyager calls over the client's one transport; no retries, no hidden paging."""

    def __init__(self, transport: Transport) -> None:
        self.transport = transport

    @property
    def owner(self) -> str:
        """The session's device ID, which ties page cursors to this session."""
        return self.transport.session.device_id

    async def query(
        self,
        query: GraphQLQuery,
        variables: Mapping[str, object] | None = None,
        *,
        ignore_null_field_errors: bool = False,
    ) -> dict[str, Any]:
        """Run a read and return its `data` object.

        Some finders report a null in a field they declare non-null next to complete data.
        `ignore_null_field_errors` accepts those replies; any other error still raises.
        """
        params = f"variables={restli.encode(variables)}&" if variables else ""
        path = f"/voyager/api/graphql?{params}queryId={query.id}&queryName={query.name}"
        response = await self.transport.request("GET", path, headers=_GRAPHQL)
        envelope = self.transport.json_object(response)
        if ignore_null_field_errors and isinstance(envelope.get("data"), dict):
            errors = envelope.get("errors")
            if isinstance(errors, list) and all(map(_null_field_error, errors)):
                envelope = {"data": envelope["data"]}
        return _graphql_data(envelope)

    async def mutate(self, query: GraphQLQuery, variables: Mapping[str, object]) -> dict[str, Any]:
        """Run a write once and return its `data` object; a timeout leaves the outcome unknown."""
        path = f"/voyager/api/graphql?action=execute&queryId={query.id}&queryName={query.name}"
        body = {"queryId": query.id, "queryName": query.name, "variables": dict(variables)}
        response = await self.transport.request("POST", path, json=body, headers=_GRAPHQL)
        envelope = self.transport.json_object(response)
        value = envelope.get("value")
        if not isinstance(value, dict):
            raise ProtocolError("GraphQL action reply had no value object.")
        return _graphql_data(value)

    async def get(
        self, resource: str, params: Mapping[str, object] | None = None
    ) -> dict[str, Any]:
        """Read a rest.li resource such as `voyagerJobsDashJobPostings/<id>`."""
        response = await self.transport.request(
            "GET", _resource_path(resource, params), headers=_JSON
        )
        return self.transport.json_object(response)

    async def post(
        self,
        resource: str,
        body: Mapping[str, object],
        params: Mapping[str, object] | None = None,
    ) -> Reply:
        """Create or run a rest.li action once; the server may reply with no body."""
        response = await self.transport.request(
            "POST", _resource_path(resource, params), json=dict(body), headers=_JSON
        )
        data = self.transport.json_object(response) if response.content else {}
        created = response.headers.get("x-restli-id") or response.headers.get("x-linkedin-id")
        return Reply(data, created)

    async def delete(self, resource: str, params: Mapping[str, object] | None = None) -> None:
        """Delete a rest.li entity once."""
        await self.transport.request("DELETE", _resource_path(resource, params), headers=_JSON)


def _resource_path(resource: str, params: Mapping[str, object] | None) -> str:
    if not re.fullmatch(r"voyager[A-Za-z]+(/[A-Za-z0-9%()_:.,'\-~!*]+)*", resource):
        raise ValueError("A Voyager resource name such as voyagerJobsDashJobPostings is required.")
    path = "/voyager/api/" + resource
    if params:
        query = "&".join(
            f"{key}={value if isinstance(value, str) and key in _RAW else restli.encode(value)}"
            for key, value in params.items()
            if value is not None
        )
        path += "?" + query
    return path


# Plain query parameters the app writes without rest.li value encoding.
_RAW = frozenset({"q", "action", "decorationId"})


def _null_field_error(error: object) -> bool:
    if not isinstance(error, dict) or not isinstance(error.get("extensions"), dict):
        return False
    return bool(error["extensions"].get("classification") == "NullValueInNonNullableField")


def _graphql_data(envelope: dict[str, Any]) -> dict[str, Any]:
    errors = envelope.get("errors")
    if errors:
        reasons = tuple(
            str(error.get("message"))[:300]
            for error in errors
            if isinstance(error, dict) and error.get("message")
        )
        raise OperationRejected(reasons)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise ProtocolError("GraphQL reply had no data object.")
    return data
