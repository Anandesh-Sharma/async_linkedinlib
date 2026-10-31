"""Typed member identity, independent of HTTP and persistence."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Member:
    """Identity returned by the authenticated mobile SSO endpoint."""

    id: str
    first_name: str
    last_name: str
    full_name: str
    headline: str
