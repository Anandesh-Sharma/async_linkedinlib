<p align="center">
  <img src="https://raw.githubusercontent.com/Anandesh-Sharma/async_linkedinlib/main/assets/banner.png" alt="async_linkedinlib — Async Python for LinkedIn" width="100%">
</p>

# async_linkedinlib

**LinkedIn, from Python. Async by default.**

[![PyPI](https://img.shields.io/pypi/v/async_linkedinlib?color=111111)](https://pypi.org/project/async_linkedinlib/)
[![CI](https://github.com/Anandesh-Sharma/async_linkedinlib/actions/workflows/ci.yml/badge.svg)](https://github.com/Anandesh-Sharma/async_linkedinlib/actions/workflows/ci.yml)
[![MIT](https://img.shields.io/badge/license-MIT-111111)](https://github.com/Anandesh-Sharma/async_linkedinlib/blob/main/LICENSE)

- Read your feed and publish posts.
- Manage comments and reactions.
- Search people, companies and jobs.

## Get started

Python 3.11+ · macOS or Linux.

```sh
pip install async_linkedinlib
```

Import your own LinkedIn session cookies through the hidden prompts.

```sh
async-linkedinlib import-session --session ~/.async_linkedinlib.session.json
```

Read your feed:

```python
import asyncio
from async_linkedinlib import LinkedIn

async def main():
    async with LinkedIn.from_session_file("~/.async_linkedinlib.session.json") as linkedin:
        feed = await linkedin.feed.home(count=5)
        for post in feed.items:
            print(post.text)

asyncio.run(main())
```

[More examples](https://github.com/Anandesh-Sharma/async_linkedinlib/tree/main/examples) ·
[Usage & reference](https://github.com/Anandesh-Sharma/async_linkedinlib/blob/main/src/async_linkedinlib/README.md) ·
[Report an issue](https://github.com/Anandesh-Sharma/async_linkedinlib/issues)

<sub>Unofficial client. Not affiliated with LinkedIn. Private APIs can change.</sub>
