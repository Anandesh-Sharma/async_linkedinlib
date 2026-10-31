"""Exercise actual HTTP framing, compression, forms and cookies without contacting LinkedIn."""

import gzip
import json
import threading
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs

import httpx

from async_linkedinlib import LinkedIn
from async_linkedinlib import Session


class LoopbackTransport(httpx.AsyncBaseTransport):
    """Route only the fixed LinkedIn origin to a real local HTTP fixture."""

    def __init__(self, port):
        self.port = port
        self.inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request):
        assert str(request.url).startswith("https://www.linkedin.com/")
        local = request.url.copy_with(scheme="http", host="127.0.0.1", port=self.port)
        forwarded = httpx.Request(
            request.method, local, headers=request.headers, content=await request.aread()
        )
        return await self.inner.handle_async_request(forwarded)

    async def aclose(self):
        await self.inner.aclose()


async def test_real_http_login_and_saved_session_reuse(member_data, tmp_path):
    observed = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, payload, cookies=()):
            body = gzip.compress(json.dumps(payload).encode())
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            for cookie in cookies:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            observed.append(("GET", self.path, dict(self.headers), None))
            if self.path == "/mob/tracking":
                self.respond(None, ["bcookie=fresh; Domain=.linkedin.com; Path=/; Secure"])
            else:
                self.respond(member_data)

        def do_POST(self):
            data = self.rfile.read(int(self.headers["Content-Length"]))
            observed.append(("POST", self.path, dict(self.headers), parse_qs(data.decode())))
            self.respond(
                {"login_result": "PASS", "challenge_url": ""},
                [
                    "li_at=loopback-secret; Domain=.www.linkedin.com; Path=/; Secure; HttpOnly",
                    'JSESSIONID="ajax:loopback"; Domain=.www.linkedin.com; Path=/; Secure',
                ],
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    path = tmp_path / "session.json"
    try:
        async with LinkedIn.from_session_file(
            path, transport=LoopbackTransport(server.server_port)
        ) as client:
            assert (await client.auth.login_google("synthetic-token")).id == "12345"
        async with LinkedIn.from_session_file(
            path, transport=LoopbackTransport(server.server_port)
        ) as client:
            assert (await client.account.me()).full_name == "Test Member"
        assert [(m, p) for m, p, _, _ in observed] == [
            ("GET", "/mob/tracking"),
            ("POST", "/uas/authenticate"),
            ("GET", "/mob/sso/you"),
            ("GET", "/mob/sso/you"),
        ]
        assert observed[1][3]["googleIdToken"] == ["synthetic-token"]
        for _, _, headers, _ in observed[2:]:
            lower = {k.lower(): v for k, v in headers.items()}
            assert lower["csrf-token"] == "ajax:loopback"
            assert "li_at=loopback-secret" in lower["cookie"]
        assert Session.load(path).authenticated
        assert "synthetic-token" not in path.read_text()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
