"""Caller-controlled connection settings."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClientOptions:
    """Connection settings; one client owns one connection pool."""

    timeout: float = 30.0
    max_connections: int = 1

    def __post_init__(self) -> None:
        if self.timeout <= 0 or self.max_connections < 1:
            raise ValueError("Timeout and connection count must be positive.")
