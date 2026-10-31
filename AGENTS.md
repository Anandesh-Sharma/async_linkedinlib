# Rules for async_linkedinlib

Follow these standalone library rules.
Read the [root README](README.md), [package reference](src/async_linkedinlib/README.md), relevant source, and tests before editing.
Keep this a standalone Python package; do not import the backend or `async_instalib`.

## README style

Keep the root README a short showcase: the benefit, a few features, installation,
and one complete quick-start example. Link to examples and the
[package README](src/async_linkedinlib/README.md) for API details, limitations, verification,
architecture, contribution instructions and release steps. Do not expand the
front page into API documentation. Update the package README when behavior changes.

## Structure and ownership

- `client.py` owns `LinkedIn`, the shared session/transport, resource construction,
  async lifecycle and session-file ownership. Add an explicit attribute for each
  implemented resource; keep endpoint logic out of this class.
- `auth/` owns login orchestration, fresh login context and supported challenge
  handling. It may reuse the account resource to verify a completed login.
- `session/` owns account/device state, scoped cookies, persistence and file locks.
  It performs no HTTP requests. Do not store passwords or Google ID tokens here.
- `transport/` is the single network boundary. `http.py` owns the HTTPX pool,
  authentication headers, cookie updates, timeouts, HTTP error translation and cooldowns.
  `voyager.py` runs persisted GraphQL operations and rest.li calls over it, and `restli.py`
  encodes variables exactly as the app's `DataEncoder` does.
- `resources/` owns feature operations and provider-response decoding. Every
  resource receives the existing transport; never create a separate session or
  HTTP client per feature.
- `models/` owns typed public results. Models perform no network or persistence work.
- `config/` owns caller options and versioned app metadata, separate from credentials.
- `exceptions.py` owns public errors; `cli.py` owns interactive commands and credential
  input. Put runnable usage examples in `examples/`.

Group methods around a user's feature: account, feed, posts, comments, search, jobs, and
later connections and messages. Shared by several features: `resources/reactions.py`
(react and list reactions), `resources/paging.py` (every list's pages and cursors; follow the
app's pager, never write another), `resources/threads.py` (thread URNs) and
`resources/mentions.py` (text mentions). `models/content.py` holds the shared `Post`, `Author` and
`SocialCounts`; `models/pagination.py` holds `Page` and `Cursor`.
A small feature can start as `resources/<feature>.py`. Split a substantial feature
into `resources/<feature>/` when its real responsibilities justify that split.
Matching result models belong in `models/<feature>.py`; tests belong under that
feature in `tests/`. Do not pre-create empty resources, generic CRUD methods, plugin
registries, base resource classes or speculative interfaces.

Use cohesive classes and explicit dependencies. Keep public imports stable:
`from async_linkedinlib import LinkedIn, Session, Member` must continue working.
Keep `__init__.py` files declarative, with `__all__` and a one-line purpose comment
on each re-export. Annotate public APIs, use familiar names, follow Ruff's 100-column
format and a 500-line source file limit.

## Adding a LinkedIn feature

1. Establish the operation from a captured exchange or from the shipped app's own request
   code (decompiled Voyager GraphQL clients, routes and builders). App 4.1.1267 draws these
   screens with server-driven protobuf (SDUI); the SDK does not parse SDUI UI trees and uses
   the Voyager operations the same APK ships, over JSON. Take variable names, enums and
   bodies from app code: the server silently ignores unknown variables. Record the app
   version and evidence in the package README. Distinguish observed behavior, locally tested
   behavior and live SDK verification.
2. Define the smallest useful public method, typed result and expected failures.
   Keep IDs as strings. Preserve unknown versus absent fields rather than guessing.
3. Implement request construction and decoding inside the feature, using the shared
   transport. Do not spread provider payloads and URL construction through `client.py`.
4. Test the request contract and meaningful failures with synthetic data. Use a real
   loopback server when serialization, cookies, streaming or lifecycle matters.
5. Update the package README's feature coverage, usage and limits. Add root exports only for
   supported public types. An observed endpoint does not establish every capability
   or variation of that feature.

Intended future groups are `connections` and `messages`. These names describe extension
boundaries, not implemented functionality. Implement only the feature requested.

## Protocol and account state

- `li_at` is the primary session credential; preserve `JSESSIONID` and its CSRF role.
  Retain cookie domain, path, security and expiry when available. Never flatten the
  entire jar into a global credential header or send it to arbitrary hosts.
- Each client owns one account and one connection pool. New features must use the
  same cookie rotation and cooldown behavior. Preserve saved-session compatibility;
  version persisted schema changes explicitly.
- Google sign-in currently means exchanging a caller-supplied fresh ID token for
  LinkedIn's Android flow. Do not imply that the SDK acquires Google tokens or accepts
  tokens issued for unrelated OAuth clients. Do not replay a captured login token.
- Do not invent endpoints, GraphQL IDs, token refresh, OTP, password login, challenge
  continuation or anti-abuse telemetry. Unsupported server flows fail explicitly.
- Keep pagination explicit. Preserve opaque server cursors and their account/query
  context (`Cursor` carries the operation, query scope and owning session); do not
  silently fetch every page or invent continuation values.
- A write whose 2xx reply cannot be read raises `UnconfirmedWrite`, never a plain
  `ProtocolError`, so callers know the change may exist.
- Reads must not implicitly send messages, mark conversations read, follow, connect,
  apply for jobs, publish, delete or acknowledge content. Expose those actions as
  separate, clearly named operations when supported by evidence.
- Never silently retry a write or credential exchange. A timeout can occur after the
  server accepted it. Do not assume an idempotency mechanism exists.
- Keep TLS verification enabled, redirects explicit, and destination hosts constrained
  to the documented operation. Uploads observed so far go to www.linkedin.com; validate an
  upload URL's host before sending. Add another host only when its flow requires it, with
  credentials scoped to that host.
- Accept GraphQL replies with errors only through `Voyager.query(...,
  ignore_null_field_errors=True)`, and only for finders known to report harmless nulls.

## Credentials and verification

Keep raw captures, cookies, passwords, ID tokens and real account data outside Git.
Use hidden prompts or caller-provided secret inputs, never credential arguments.
Session files remain atomic and mode 0600; preserve exclusive file ownership.
Logs, exception messages and object reprs must not expose secrets or raw responses.
Challenge URLs can carry private state and must not appear in ordinary error text.

Use synthetic credentials in tests. Live reads must use the user's authorized
session. Live writes require an authorized action and target; preserve that
authorization across turns rather than asking repeatedly. Delete test-created remote data, verify cleanup, and report any effects that cannot be undone.

Run checks from this directory:

```sh
uv run pytest -q
uv run ruff check src tests examples
uv run ruff format --check src tests examples
uv run mypy src
uv build
```

Use focused tests while developing, then the full package suite for changes to
auth, transport, sessions or public imports. Do not contact LinkedIn in the normal
test suite. Report live and simulated verification separately. Keep detailed
documentation in the package README and these rules; plans belong in `tasks/`. Do not create a separate documentation site.

## After pushing

After every push, wait for all triggered CI/CD runs for that exact commit to pass.
Fix failures and recheck before declaring completion; report any external blocker.
