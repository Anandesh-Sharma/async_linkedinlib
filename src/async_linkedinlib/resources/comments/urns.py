"""The URN forms of posts and comments that the comment operations exchange.

A comment has two spellings, both seen in every comment the server returns:
`urn:li:comment:(activity:<post>,<id>)` (its social thread, for reactions and replies) and
`urn:li:fsd_comment:(<id>,urn:li:activity:<post>)` (the entity that is edited or deleted).
Replies use the post as their thread too, never the parent comment.
"""

import re
from dataclasses import dataclass

_COMMENT = re.compile(r"urn:li:comment:\(([A-Za-z]+:[0-9]+),([0-9]+)\)")
_ENTITY = re.compile(r"urn:li:fsd_comment:\(([0-9]+),urn:li:([A-Za-z]+:[0-9]+)\)")


@dataclass(frozen=True, slots=True)
class CommentUrn:
    """A comment identified by its post thread (`activity:<id>`) and its own ID."""

    thread: str
    id: str

    @classmethod
    def parse(cls, urn: str) -> "CommentUrn":
        """Accept either spelling of a comment URN."""
        if isinstance(urn, str):
            if found := _COMMENT.fullmatch(urn):
                return cls(found[1], found[2])
            if found := _ENTITY.fullmatch(urn):
                return cls(found[2], found[1])
        raise ValueError("A comment URN such as urn:li:comment:(activity:<id>,<id>) is required.")

    @property
    def urn(self) -> str:
        return f"urn:li:comment:({self.thread},{self.id})"

    @property
    def entity_urn(self) -> str:
        return f"urn:li:fsd_comment:({self.id},urn:li:{self.thread})"

    @property
    def post_urn(self) -> str:
        return f"urn:li:{self.thread}"
