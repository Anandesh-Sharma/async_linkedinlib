"""Read what a test request sent: GraphQL query parameters and rest.li-encoded variables."""

import re
from urllib.parse import parse_qs
from urllib.parse import unquote

import httpx


def decode(raw: str) -> object:
    """Decode a rest.li value into dicts, lists and strings, as the server reads it."""
    value, rest = _value(raw)
    assert rest == "", rest
    return value


def variables(request: httpx.Request) -> object:
    """The decoded `variables` of a GraphQL GET; scalars come back as strings."""
    query = request.url.query.decode()
    raw = next(part for part in query.split("&") if part.startswith("variables="))
    return decode(raw.removeprefix("variables="))


def params(request: httpx.Request) -> dict[str, str]:
    """The plain query parameters (queryId, queryName, action...), without `variables`."""
    query = request.url.query.decode()
    return {key: values[0] for key, values in parse_qs(query).items() if key != "variables"}


def _value(raw: str) -> tuple[object, str]:
    if raw.startswith("List("):
        found: list = []
        raw = raw[5:]
        while not raw.startswith(")"):
            item, raw = _value(raw)
            found.append(item)
            raw = raw.removeprefix(",")
        return found, raw[1:]
    if raw.startswith("("):
        record: dict = {}
        raw = raw[1:]
        while not raw.startswith(")"):
            key, _, raw = raw.partition(":")
            record[key], raw = _value(raw)
            raw = raw.removeprefix(",")
        return record, raw[1:]
    token = re.match(r"[^(),:]*", raw).group(0)
    return ("" if token == "''" else unquote(token)), raw[len(token) :]
