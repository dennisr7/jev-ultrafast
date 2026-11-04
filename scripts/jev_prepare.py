"""Prepare Haiku-supervised Jev runs for a list of Greenhouse postings, in one command.

uv run python scripts/jev_prepare.py <board> <job id> [<job id> ...] [--runs DIR] [--resume PATH]

For each posting it:
- detects whether the form has MyGreenhouse Autofill (the board's own job page) or not (boards that redirect to
  their company site: then the standalone embed form is used, Jev types the contact details, and the runner
  attaches --resume),
- builds goal.txt from the posting's own questions (scripts/jev_greenhouse_goal.py); a required question with no
  known answer holds that posting back (listed, never guessed),
- writes meta.json and brief.txt (from .claude/skills/supervise-jev/haiku-brief-template.txt) and clears old run files.

It prints, for each ready posting, the one-line prompt to give a Haiku subagent (Agent tool, model "haiku").
Claude launches those agents; afterwards check every run with scripts/jev_check_runs.py.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from jev_greenhouse_goal import build_goal, fetch_posting
from profile_guard import require_primary

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / ".claude/skills/supervise-jev/haiku-brief-template.txt"
DEFAULT_RESUME = ROOT.parent / "cv" / "Alex Van Sample.pdf"
STALE = ("log.jsonl", "result.json", "control", "review.jsonl", "stdout.txt", "final.jpg", "tabs_before.json",
         "requests.jsonl")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def has_autofill_button(url):
    """Whether the page actually shows MyGreenhouse's "Autofill my application" button (some boards disable it)."""
    sys.path.insert(0, str(ROOT))
    import time
    from jev_ultrafast.browser import Browser
    browser = Browser(url)
    try:
        for _ in range(20):
            if browser.evaluate("[...document.querySelectorAll('button,a,[role=button]')]"
                                ".some(e => /autofill my application/i.test(e.innerText))"):
                return True
            time.sleep(0.25)
        return False
    finally:
        browser.close()


def form_url(board, job, cache={}):
    """(url, has_autofill): the board's own job page if Greenhouse serves it, else the standalone embed form.

    Autofill is checked on the live page once per board (all of a board's postings share the setting).
    """
    page = f"https://job-boards.greenhouse.io/{board}/jobs/{job}"
    try:
        urllib.request.build_opener(NoRedirect).open(page, timeout=20)
    except urllib.error.HTTPError as error:
        if error.code in (301, 302, 303, 307, 308):
            return f"https://job-boards.greenhouse.io/embed/job_app?for={board}&token={job}", False
        raise
    if board not in cache:
        cache[board] = has_autofill_button(page)
    return page, cache[board]


def main():
    require_primary()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("board")
    parser.add_argument("jobs", nargs="+")
    parser.add_argument("--runs", help="Folder for the run folders (default artifacts/<board>).")
    parser.add_argument("--resume", default=str(DEFAULT_RESUME), help="Attached on forms without Autofill.")
    args = parser.parse_args()
    runs = Path(args.runs) if args.runs else ROOT / "artifacts" / args.board
    resume = Path(args.resume).resolve()
    template = TEMPLATE.read_text()
    ready, held = [], []
    for job in args.jobs:
        posting = fetch_posting(args.board, job)
        url, autofill = form_url(args.board, job)
        goal, unknown = build_goal(posting, autofill)
        if unknown:
            held.append((job, posting["title"], unknown))
            continue
        if not autofill and not resume.is_file():
            sys.exit(f"Resume not found: {resume}")
        run = runs / str(job)
        run.mkdir(parents=True, exist_ok=True)
        for name in STALE:
            (run / name).unlink(missing_ok=True)
        attach = [] if autofill else [f"resume={resume}"]
        company = posting.get("company_name") or args.board
        (run / "goal.txt").write_text(goal)
        (run / "meta.json").write_text(json.dumps({
            "board": args.board, "job_id": str(job), "title": posting["title"], "company": company,
            "url": url, "autofill": autofill, "attach": attach}, indent=1))
        rel = run.relative_to(ROOT) if run.is_relative_to(ROOT) else run
        brief = (template.replace("__COMPANY__", company).replace("__TITLE__", posting["title"])
                 .replace("__URL__", url).replace("__RUN__", str(rel))
                 .replace("__ATTACH__", "".join(f'--attach "{a}" ' for a in attach))
                 .replace("__ATTACH_NOTE__",
                          "   The runner attaches the resume itself before Jev's first decision (an \"attached\" "
                          "event). If it reports an error instead, stop and report it." if attach else
                          "   This form has MyGreenhouse Autofill: approve Jev clicking \"Autofill my application\"."))
        (run / "brief.txt").write_text(brief)
        ready.append((job, posting["title"], autofill, run))

    print(f"Ready: {len(ready)}   Held for answers: {len(held)}\n")
    for job, title, autofill, run in ready:
        print(f"  {job}  {title[:60]}  ({'Autofill' if autofill else 'no Autofill: typed contact + resume attach'})")
    for job, title, unknown in held:
        print(f"  HELD {job}  {title[:55]}: needs the user's answer to:")
        for label in unknown:
            print(f"      - {label[:110]}")
    if ready:
        print("\nHaiku prompts (Agent tool, model \"haiku\", one agent per line; run a few at a time):")
        for job, title, autofill, run in ready:
            print(f"  [{job}] Read {run / 'brief.txt'} and follow it exactly. It is your complete task: supervising "
                  "the Jev browser agent while it fills a job application form, approving or rejecting each step, "
                  "never submitting, then verifying and reporting.")
        print(f"\nAfterwards: uv run python scripts/jev_check_runs.py {' '.join(str(r) for *_, r in ready)}")
    return 3 if held else 0


if __name__ == "__main__":
    sys.exit(main())
