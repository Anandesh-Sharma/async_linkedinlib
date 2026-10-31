"""Public client lifecycle and exclusive session-file ownership."""

import asyncio
from pathlib import Path
from types import TracebackType
from typing import Self

import httpx

from .auth import Auth
from .config import ClientOptions
from .resources import Account
from .resources import Comments
from .resources import Feed
from .resources import Jobs
from .resources import Posts
from .resources import Search
from .session import Session
from .session.lease import SessionLease
from .transport import Transport
from .transport import Voyager


class LinkedIn:
    """One account per async context; closing saves state without logging out."""

    def __init__(
        self,
        session: Session | None = None,
        options: ClientOptions | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.session = session if session is not None else Session()
        self._transport = Transport(self.session, options or ClientOptions(), transport)
        self.auth = Auth(self._transport)
        self.account = Account(self._transport)
        voyager = Voyager(self._transport)
        self.feed = Feed(voyager)
        self.posts = Posts(voyager)
        self.comments = Comments(voyager)
        self.search = Search(voyager)
        self.jobs = Jobs(voyager)
        self._lease: SessionLease | None = None
        self._closed = False
        self._close_lock = asyncio.Lock()

    @classmethod
    def from_session_file(
        cls,
        path: str | Path,
        options: ClientOptions | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> Self:
        destination = Path(path).expanduser().resolve()
        lease = SessionLease(destination)
        try:
            session = Session.load(destination) if destination.exists() else Session()
            if not destination.exists():
                session.save(destination)
            client = cls(session, options, transport)
            client._lease = lease
            client._transport.session_file = destination
            return client
        except BaseException:
            lease.close()
            raise

    async def __aenter__(self) -> Self:
        if self._closed:
            raise RuntimeError("LinkedIn client is closed.")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            try:
                await self._transport.aclose()
            finally:
                try:
                    self._transport.checkpoint()
                finally:
                    self._closed = True
                    if self._lease is not None:
                        self._lease.close()
