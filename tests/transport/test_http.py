from datetime import UTC
from datetime import datetime
from datetime import timedelta
from email.utils import format_datetime

import httpx
import pytest

from async_linkedinlib import AuthenticationError
from async_linkedinlib import ChallengeRequired
from async_linkedinlib import HTTPError
from async_linkedinlib import LinkedIn
from async_linkedinlib import NetworkError
from async_linkedinlib import ProtocolError
from async_linkedinlib import RateLimited
from async_linkedinlib import Session


async def test_saved_cookie_pair_authenticates_without_login(session, member_data, tmp_path):
    path = tmp_path / "session.json"
    session.save(path)
    calls = []

    def handle(request):
        calls.append(request)
        assert request.url.path == "/mob/sso/you"
        assert request.headers["csrf-token"] == "ajax:1234567890123456789"
        assert "li_at=test-session-secret" in request.headers["cookie"]
        return httpx.Response(
            200,
            json=member_data,
            headers=[
                ("set-cookie", "li_at=rotated; Domain=.www.linkedin.com; Path=/; Secure"),
                ("set-cookie", 'JSESSIONID="ajax:next"; Domain=.www.linkedin.com; Path=/; Secure'),
            ],
        )

    async with LinkedIn.from_session_file(path, transport=httpx.MockTransport(handle)) as client:
        assert (await client.account.me()).id == "12345"
    assert len(calls) == 1
    restored = Session.load(path)
    assert restored.cookie_value("li_at") == "rotated"
    assert restored.cookie_value("JSESSIONID").strip('"') == "ajax:next"


async def test_401_clears_stale_auth_and_blocks_next_read(session, tmp_path):
    path = tmp_path / "session.json"
    session.save(path)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(401, text="private-server-body")

    async with LinkedIn.from_session_file(path, transport=httpx.MockTransport(handle)) as client:
        for _ in range(2):
            with pytest.raises(AuthenticationError) as caught:
                await client.account.me()
            assert "private-server-body" not in str(caught.value)
        assert not client.session.authenticated
    assert len(calls) == 1
    assert not Session.load(path).authenticated


@pytest.mark.parametrize(
    "retry", ["120", format_datetime(datetime.now(UTC) + timedelta(seconds=120)), "bad"]
)
async def test_rate_limit_blocks_calls_and_survives_reload(session, tmp_path, retry):
    path = tmp_path / "session.json"
    session.save(path)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(429, headers={"retry-after": retry})

    transport = httpx.MockTransport(handle)
    async with LinkedIn.from_session_file(path, transport=transport) as client:
        for _ in range(2):
            with pytest.raises(RateLimited) as caught:
                await client.account.me()
            assert caught.value.retry_after > 0
    async with LinkedIn.from_session_file(path, transport=transport) as client:
        with pytest.raises(RateLimited):
            await client.account.me()
    assert len(calls) == 1


@pytest.mark.parametrize(
    "status,error", [(403, ChallengeRequired), (302, ProtocolError), (500, HTTPError)]
)
async def test_http_failures_are_not_retried_or_followed(session, status, error):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            status,
            text="private-cookie-value",
            headers={"location": "https://outside.example/?secret=private-cookie-value"},
        )

    async with LinkedIn(session, transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(error) as caught:
            await client.account.me()
        assert "private-cookie-value" not in str(caught.value)
    assert len(calls) == 1


async def test_network_failure_does_not_retry_or_expose_httpx_error(session):
    calls = []

    def handle(request):
        calls.append(request)
        raise httpx.ConnectError("private-secret-in-original-error", request=request)

    async with LinkedIn(session, transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(NetworkError) as caught:
            await client.account.me()
        assert "private-secret" not in repr(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize("body", [b"<html>private</html>", b"[]", b"{}", b'{"memberID":true}'])
async def test_invalid_member_responses_fail_closed(session, body):
    async with LinkedIn(
        session, transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    ) as client:
        with pytest.raises(ProtocolError):
            await client.account.me()


async def test_cookie_deletion_and_identity_mismatch(session, member_data):
    session.member_id = "different-member"
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=member_data))
    async with LinkedIn(session, transport=transport) as client:
        with pytest.raises(AuthenticationError):
            await client.account.me()
        assert not session.authenticated


async def test_expired_server_cookie_is_not_sent_again(session, member_data):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            200,
            json=member_data,
            headers={"set-cookie": "li_at=; Max-Age=0; Domain=.www.linkedin.com; Path=/; Secure"},
        )

    async with LinkedIn(session, transport=httpx.MockTransport(handle)) as client:
        await client.account.me()
        assert not session.authenticated
        with pytest.raises(AuthenticationError):
            await client.account.me()
    assert len(calls) == 1
