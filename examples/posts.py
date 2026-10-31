"""Post to connections (optionally with an image) and delete it again, or list scheduled posts."""

import argparse
import asyncio
from pathlib import Path

from async_linkedinlib import Image
from async_linkedinlib import LinkedIn
from async_linkedinlib import MediaKind
from async_linkedinlib import Visibility


async def main(path: Path, text: str | None, image: Path | None, keep: bool) -> None:
    async with LinkedIn.from_session_file(path) as linkedin:
        if text is None:
            page = await linkedin.posts.scheduled(count=10)
            for post in page.items:
                print(f"{post.publish_at:%Y-%m-%d %H:%M} UTC  {post.share_urn}  {post.text}")
            if not page.items:
                print("No scheduled posts.")
            return
        media = None
        if image is not None:
            uploaded = await linkedin.posts.media.upload(image, MediaKind.IMAGE)
            media = Image(uploaded, alt_text=image.stem)
        shared = await linkedin.posts.create(
            text, visibility=Visibility.CONNECTIONS_ONLY, media=media
        )
        print(f"{shared.message or 'Posted.'} {shared.share_urn} ({shared.activity_urn})")
        if not keep:
            await linkedin.posts.delete(shared.share_urn)
            print("Deleted it again.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--text", help="post this text; without it, list scheduled posts")
    parser.add_argument("--image", type=Path, help="attach this image file")
    parser.add_argument("--keep", action="store_true", help="do not delete the new post")
    args = parser.parse_args()
    asyncio.run(main(args.session, args.text, args.image, args.keep))
