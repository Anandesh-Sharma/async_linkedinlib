"""Read a post's comments, or comment on it and then delete that comment again."""

import argparse
import asyncio
from pathlib import Path

from async_linkedinlib import Comment
from async_linkedinlib import CommentSort
from async_linkedinlib import LinkedIn


def show(comment: Comment, indent: str = "") -> None:
    name = comment.author.name if comment.author else "?"
    print(f"{indent}{name}: {comment.text} ({comment.counts.reactions} reactions)")


async def main(path: Path, post_urn: str, sort: CommentSort, comment_text: str | None) -> None:
    async with LinkedIn.from_session_file(path) as linkedin:
        if comment_text:
            comment = await linkedin.comments.create(post_urn, comment_text)
            print(f"Created {comment.urn}")
            await linkedin.comments.delete(comment.urn)
            print("Deleted it again.")
            return
        page = await linkedin.comments.list(post_urn, sort=sort, count=10)
        for comment in page.items:
            show(comment)
            for reply in comment.replies:
                show(reply, "    ")
        if page.next:
            print(f"More comments follow; pass page.next to list() to continue ({page.total}).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--post", required=True, help="thread URN, e.g. urn:li:activity:<id>")
    parser.add_argument("--recent", action="store_true", help="newest first")
    parser.add_argument("--comment", help="post this text, then delete it")
    args = parser.parse_args()
    order = CommentSort.RECENT if args.recent else CommentSort.RELEVANCE
    asyncio.run(main(args.session, args.post, order, args.comment))
