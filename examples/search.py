"""Search people, posts and jobs near a place, resolving the place through typeahead."""

import argparse
import asyncio
from pathlib import Path

from async_linkedinlib import DatePosted
from async_linkedinlib import JobDatePosted
from async_linkedinlib import JobFilters
from async_linkedinlib import LinkedIn
from async_linkedinlib import PeopleFilters
from async_linkedinlib import PostFilters
from async_linkedinlib import PostSort
from async_linkedinlib import TypeaheadKind


async def show_search(linkedin: LinkedIn, keywords: str, place: str) -> None:
    search = linkedin.search
    places = await search.typeahead(TypeaheadKind.GEO, place, count=1)
    if not places or not places[0].id:
        print(f"No location matches {place!r}.")
        return
    geo = places[0]
    print(f"Location: {geo.title} (geo {geo.id})")

    people = await search.people(keywords, PeopleFilters(locations=[geo.id]))
    print(f"\nPeople: about {people.total}")
    for person in people.items[:5]:
        print(f"  {person.name} - {person.headline} ({person.distance})")

    recent = PostFilters(sort_by=PostSort.LATEST, date_posted=DatePosted.PAST_WEEK)
    posts = await search.posts(keywords, recent, count=5)
    print(f"\nPosts this week: about {posts.total}")
    for post in posts.items:
        author = post.author.name if post.author else "unknown"
        print(f"  {author}, {post.age}: {(post.text or '')[:70]!r}")

    filters = JobFilters(location=geo.id, easy_apply=True, date_posted=JobDatePosted.PAST_WEEK)
    jobs = await search.jobs(keywords, filters, count=10)
    print(f"\nEasy Apply jobs this week: {jobs.total}")
    for job in jobs.items:
        print(f"  {job.title} at {job.company}, {job.location} (job {job.id})")
    if jobs.next:
        more = await search.jobs(keywords, filters, count=10, cursor=jobs.next)
        print(f"  ... next page: {len(more.items)} more")


async def main(path: Path, keywords: str, place: str) -> None:
    async with LinkedIn.from_session_file(path) as linkedin:
        await show_search(linkedin, keywords, place)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--keywords", default="python developer")
    parser.add_argument("--place", default="Berlin")
    args = parser.parse_args()
    asyncio.run(main(args.session, args.keywords, args.place))
