"""Interactive credentials; never put tokens in command arguments or shell history."""

import argparse
import asyncio
from getpass import getpass
from pathlib import Path

from .client import LinkedIn
from .exceptions import LinkedInError
from .session import Session


async def run(command: str, path: Path) -> None:
    async with LinkedIn.from_session_file(path) as client:
        if command == "import-session":
            if client.session.cookies:
                raise LinkedInError("Session file already contains cookies; choose a new file.")
            imported = Session.from_cookies(getpass("li_at: "), getpass("JSESSIONID: "))
            client.session.cookies = imported.cookies
            member = await client.account.me()
        elif command == "login-google" and not client.session.authenticated:
            member = await client.auth.login_google(getpass("Fresh Google ID token: "))
        else:
            member = await client.account.me()
        print(f"Verified {member.full_name} (member {member.id}).")
        print(f"Session saved to {path}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("import-session", "login-google", "me"))
    parser.add_argument("--session", type=Path, required=True)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.command, args.session.expanduser()))
    except (LinkedInError, OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
