"""Read the main feed or the saved posts, or save a post and then unsave it again."""

import argparse
import asyncio
from pathlib import Path

from async_linkedinlib import FeedSort
from async_linkedinlib import LinkedIn
from async_linkedinlib import Post


def show(post: Post) -> None:
    name = post.author.name if post.author else "?"
    context = f"[{post.context}] " if post.context else ""
    text = (post.text or "").replace("\n", " ")[:80]
    print(f"{context}{name}: {text} ({post.counts.reactions} reactions) {post.urn}")


async def main(path: Path, sort: FeedSort | None, saved: bool, save: str | None) -> None:
    async with LinkedIn.from_session_file(path) as linkedin:
        if save:
            await linkedin.feed.save(save)
            print(f"Saved {save}")
            await linkedin.feed.unsave(save)
            print("Unsaved it again.")
            return
        if saved:
            page = await linkedin.feed.saved(count=10)
            for item in page.items:
                print(f"{item.author.name if item.author else '?'}: {item.text} {item.urn}")
            print(f"{page.total} saved posts.")
            return
        feed = await linkedin.feed.home(count=10, sort=sort)
        for post in feed.items:
            show(post)
        if feed.next:
            print("More posts follow; pass feed.next as cursor to home() to continue.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--recent", action="store_true", help="newest first")
    parser.add_argument("--saved", action="store_true", help="list saved posts")
    parser.add_argument("--save", metavar="ACTIVITY_URN", help="save this post, then unsave it")
    args = parser.parse_args()
    order = FeedSort.RECENT if args.recent else None
    asyncio.run(main(args.session, order, args.saved, args.save))
