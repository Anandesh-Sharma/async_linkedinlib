import json
import os
import time

import httpx
import pytest

from async_linkedinlib import LinkedIn
from async_linkedinlib import Session
from async_linkedinlib import SessionError
from async_linkedinlib import SessionInUse
from async_linkedinlib.session.cookies import SessionCookie


def test_private_roundtrip_preserves_scope_expiry_and_identity(session, tmp_path):
    session.cookies.append(
        SessionCookie("bcookie", "sensitive", ".linkedin.com", "/mob", True, int(time.time()) + 600)
    )
    session.member_id = "12345"
    session.rate_limit_until = time.time() + 60
    path = tmp_path / "nested" / "session.json"
    session.save(path)
    restored = Session.load(path)
    assert restored.device_id == session.device_id
    assert restored.profile == session.profile
    assert restored.cookies == session.cookies
    assert restored.rate_limit_until == session.rate_limit_until
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert "sensitive" not in repr(restored)
    assert "test-session-secret" not in repr(restored.cookies)


def test_expiry_and_path_cookie_selection(session):
    session.cookies.insert(
        0, SessionCookie("li_at", "expired", ".linkedin.com", expires=int(time.time()) - 1)
    )
    session.cookies.append(SessionCookie("li_at", "path-specific", ".www.linkedin.com", "/other"))
    assert session.cookie_value("li_at", "/mob/sso/you") == "test-session-secret"
    assert session.cookie_value("li_at", "/other/read") == "path-specific"
    assert session.cookie_value("li_at", "/otherwise") == "test-session-secret"
    jar = session.to_httpx()
    unrelated = httpx.Request("GET", "https://example.com/")
    jar.set_cookie_header(unrelated)
    assert "cookie" not in unrelated.headers
    insecure = httpx.Request("GET", "http://www.linkedin.com/")
    jar.set_cookie_header(insecure)
    assert "cookie" not in insecure.headers


@pytest.mark.parametrize(
    "payload",
    ["not-json", "[]", '{"schema_version": 2}', '{"schema_version":1,"cookies":"secret"}'],
)
def test_corrupt_session_never_silently_replaced(payload, tmp_path):
    path = tmp_path / "session.json"
    path.write_text(payload)
    with pytest.raises(SessionError):
        LinkedIn.from_session_file(path)
    assert path.read_text() == payload


async def test_exclusive_session_ownership_is_released_on_close(tmp_path):
    path = tmp_path / "session.json"
    first = LinkedIn.from_session_file(path)
    try:
        with pytest.raises(SessionInUse):
            LinkedIn.from_session_file(path)
    finally:
        await first.aclose()
    async with LinkedIn.from_session_file(path):
        pass
    await first.aclose()


def test_cookie_import_rejects_empty_and_header_injection():
    for li_at, csrf in [("", "csrf"), ("secret", ""), ("secret\r\nInjected: yes", "csrf")]:
        with pytest.raises(SessionError):
            Session.from_cookies(li_at, csrf)


def test_invalid_cookie_domain_rejected_on_load(session, tmp_path):
    path = tmp_path / "session.json"
    session.save(path)
    data = json.loads(path.read_text())
    data["cookies"][0]["domain"] = "attacker.example"
    path.write_text(json.dumps(data))
    with pytest.raises(SessionError):
        Session.load(path)
