"""Read the current member using an already saved session."""

import argparse
import asyncio
from pathlib import Path

from async_linkedinlib import LinkedIn


async def show_account(path: Path) -> None:
    async with LinkedIn.from_session_file(path) as linkedin:
        member = await linkedin.account.me()
        print(f"{member.full_name} (member {member.id})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(show_account(args.session))
