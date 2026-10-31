"""Show a job and its Easy Apply questions, list saved jobs, or build (not send) an application.

Building uploads the resume (which applies to nothing by itself) and prints the answers
the submission would carry. Nothing is submitted unless --submit is given.
"""

import argparse
import asyncio
import json
from pathlib import Path

from async_linkedinlib import LinkedIn
from async_linkedinlib import TrackedStatus


async def main(path: Path, job_id: str | None, args: argparse.Namespace) -> None:
    async with LinkedIn.from_session_file(path) as linkedin:
        if job_id is None:
            page = await linkedin.jobs.tracked(TrackedStatus.SAVED)
            for tracked in page.items:
                print(f"{tracked.id} {tracked.title} at {tracked.company} ({tracked.location})")
            print(f"{page.total} saved jobs.")
            return
        job = await linkedin.jobs.get(job_id)
        print(f"{job.title} at {job.company}, {job.location} {job.workplace_types}")
        print(f"{job.employment_type}, listed {job.listed_at}, {job.applicants_text}")
        print(f"Easy Apply: {job.easy_apply}, applied: {job.applied}, saved: {job.saved}")
        if not job.easy_apply:
            print(f"Apply on the company site: {job.apply_url}")
            return
        form = await linkedin.jobs.application(job.id)
        for question in form.questions:
            options = [option.label for option in question.options[:5]]
            required = "required" if question.required else "optional"
            print(f"- {question.label} [{question.kind}, {required}] {options or ''}")
        for slot in form.files:
            print(f"- file: {slot.label} {slot.mime_types} up to {slot.max_size} bytes")
        if not args.answers:
            return
        answers = json.loads(args.answers)
        files = {}
        if args.resume and form.files:
            files[form.files[0].id] = await linkedin.jobs.upload_file(args.resume)
        submission = linkedin.jobs.submission(form, answers, files=files, job=job)
        for label, values in submission.answers:
            print(f"{label}: {', '.join(values)}")
        if args.submit:
            status = await linkedin.jobs.submit(submission)
            print(f"Applied: {status.applied} at {status.applied_at}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--job", help="job ID; without it the saved jobs are listed")
    parser.add_argument("--answers", help='JSON object such as {"Mobile phone number": "..."}')
    parser.add_argument("--resume", type=Path, help="a .pdf, .doc or .docx resume to upload")
    parser.add_argument("--submit", action="store_true", help="really send the application")
    arguments = parser.parse_args()
    asyncio.run(main(arguments.session, arguments.job, arguments))
