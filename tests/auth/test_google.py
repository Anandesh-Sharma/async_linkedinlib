import json
from urllib.parse import parse_qs

import httpx
import pytest

from async_linkedinlib import AuthenticationError
from async_linkedinlib import ChallengeRequired
from async_linkedinlib import LinkedIn
from async_linkedinlib import NetworkError
from async_linkedinlib import ProtocolError
from async_linkedinlib import Session


async def test_google_exchange_uses_fresh_bootstrap_and_rotated_session(member_data, tmp_path):
    calls = []
    token = "synthetic-google-secret"

    def handle(request):
        calls.append(request)
        assert request.url.host == "www.linkedin.com"
        if request.url.path == "/mob/tracking":
            assert request.method == "GET"
            assert token not in str(request.headers)
            return httpx.Response(
                200,
                content=b"null",
                headers=[
                    ("set-cookie", 'bcookie="fresh-browser"; Domain=.linkedin.com; Path=/; Secure'),
                    (
                        "set-cookie",
                        'bscookie="fresh-secure"; Domain=.www.linkedin.com; Path=/; Secure',
                    ),
                    ("set-cookie", "lang=v=2&lang=en_US; Domain=.linkedin.com; Path=/; Secure"),
                ],
            )
        if request.url.path == "/uas/authenticate":
            assert request.method == "POST"
            form = parse_qs(request.content.decode())
            assert form["soogleLoginRequestType"] == ["ONE_TAP_AUTO_LOGIN"]
            assert form["googleIdToken"] == [token]
            assert form["client_enabled_features"] == ["ANDROID_NATIVE_CAPTCHA"]
            assert form["bcookie"] == ["fresh-browser"]
            assert form["bscookie"] == ["fresh-secure"]
            assert form["JSESSIONID"] == [request.headers["csrf-token"]]
            assert request.headers["csrf-token"].startswith("ajax:")
            assert (
                json.loads(request.headers["x-li-track"])["deviceId"] == request.headers["x-udid"]
            )
            return httpx.Response(
                200,
                json={"login_result": "PASS", "challenge_url": ""},
                headers=[
                    ("set-cookie", "li_at=issued-secret; Domain=.www.linkedin.com; Path=/; Secure"),
                    (
                        "set-cookie",
                        'JSESSIONID="ajax:rotated"; Domain=.www.linkedin.com; Path=/; Secure',
                    ),
                ],
            )
        assert request.url.path == "/mob/sso/you"
        assert request.headers["csrf-token"] == "ajax:rotated"
        assert "li_at=issued-secret" in request.headers["cookie"]
        assert token not in request.headers["cookie"]
        return httpx.Response(200, json=member_data)

    path = tmp_path / "account.json"
    async with LinkedIn.from_session_file(path, transport=httpx.MockTransport(handle)) as client:
        me = await client.auth.login_google(token)
        assert me.id == "12345"
        assert client.session.authenticated
        with pytest.raises(AuthenticationError):
            await client.auth.login_google("another-token")
    assert len(calls) == 3
    saved = Session.load(path)
    assert saved.member_id == "12345"
    assert saved.cookie_value("li_at") == "issued-secret"
    assert token not in path.read_text()


async def test_prepare_creates_distinct_csrf_and_device_identity():
    transport = httpx.MockTransport(lambda req: httpx.Response(200))
    async with LinkedIn(transport=transport) as first, LinkedIn(transport=transport) as second:
        await first.auth.prepare()
        await second.auth.prepare()
        assert first.session.device_id != second.session.device_id
        assert first.session.cookie_value("JSESSIONID") != second.session.cookie_value("JSESSIONID")


@pytest.mark.parametrize(
    "result,error",
    [
        ({"login_result": "FAIL", "challenge_url": ""}, AuthenticationError),
        (
            {
                "login_result": "CHALLENGE",
                "challenge_url": "https://www.linkedin.com/checkpoint/secret",
            },
            ChallengeRequired,
        ),
        ({"login_result": "PASS", "challenge_url": ""}, ProtocolError),
        ([], ProtocolError),
    ],
)
async def test_rejected_login_does_not_save_token_or_claim_success(result, error, tmp_path):
    calls = []

    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={} if request.url.path == "/mob/tracking" else result)

    path = tmp_path / "state.json"
    async with LinkedIn.from_session_file(path, transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(error) as caught:
            await client.auth.login_google("private-google-token")
        assert "private-google-token" not in str(caught.value)
        assert "checkpoint/secret" not in repr(caught.value)
        assert not client.session.authenticated
    assert "private-google-token" not in path.read_text()
    assert calls == ["/mob/tracking", "/uas/authenticate"]


async def test_verification_timeout_keeps_new_session_for_later_read():
    calls = []

    def handle(request):
        calls.append(request.url.path)
        if request.url.path == "/mob/tracking":
            return httpx.Response(200)
        if request.url.path == "/uas/authenticate":
            return httpx.Response(
                200,
                json={"login_result": "PASS"},
                headers={
                    "set-cookie": "li_at=new-secret; Domain=.www.linkedin.com; Path=/; Secure"
                },
            )
        raise httpx.ReadTimeout("private-response-text", request=request)

    async with LinkedIn(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(NetworkError) as caught:
            await client.auth.login_google("private-token")
        assert client.session.authenticated
        assert "private-response-text" not in str(caught.value)
    assert len(calls) == 3
