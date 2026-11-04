"""Print a Jev goal for one Greenhouse posting, listing only the questions that posting actually has.

uv run python scripts/jev_greenhouse_goal.py <board> <job id> [--no-autofill]

--no-autofill: for boards whose form has no MyGreenhouse "Autofill" button (e.g. Databricks, embedded on the
company site): Jev types the contact details in CONTACT, and the resume is attached with jev_task.py --attach.

Answers come from ANSWERS / LEAVE_BLANK in scripts/jev_bench.py. Every required question with no known
answer is printed to stderr as UNANSWERED and the exit code is 3: a person must supply that answer (never
guess it); until then the goal tells Jev to leave it blank.
"""

import json
import re
import sys
import urllib.request

from jev_bench import ANSWERS, LEAVE_BLANK, expected
from profile_guard import require_primary

# Filled by MyGreenhouse Autofill (verify afterwards with jev_read_form.py), so not listed for Jev.
STANDARD = {"First Name", "Last Name", "Email", "Phone", "Resume/CV", "Cover Letter",
            "LinkedIn Profile", "LinkedIn Profile URL"}


# Typed by Jev only on forms without MyGreenhouse Autofill (--no-autofill). The user's own contact details.
CONTACT = [
    ("First Name", "Alex"),
    ("Last Name", "Van Sample"),
    ("Email", "alex.sample@example.com"),
    ("Phone", "(555) 010-0100"),
    ("Location (City)", "Springfield, Florida, United States"),
    ("LinkedIn Profile", "https://www.linkedin.com/in/alex-sample"),
]

# Website / Portfolio fields get the Devpost profile, but only on forms that also ask for LinkedIn
# (otherwise the one link field should be LinkedIn). User's rule, 2026-10-11.
DEVPOST = "https://devpost.com/alexsample"
LINK_FIELD = re.compile(r"^((personal|other) )?(websites?|portfolios?)\b", re.I)


def fetch_posting(board, job):
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job}?questions=true"
    return json.load(urllib.request.urlopen(url, timeout=20))


def main(board, job, autofill=True):
    require_primary()
    goal, unknown = build_goal(fetch_posting(board, job), autofill)
    print(goal)
    for label in unknown:
        print(f"UNANSWERED required question (needs the user's answer): {label}", file=sys.stderr)
    return 3 if unknown else 0


def build_goal(posting, autofill=True):
    """(goal text, required questions with no known answer) for one posting from the Greenhouse API."""
    questions = posting["questions"]
    answers, blank, unknown = [], [], []
    if not autofill:
        # Location (City) only exists when the posting has location questions.
        contact = [c for c in CONTACT[:5] if c[0] != "Location (City)" or posting.get("location_questions")]
        answers += [f'{label} = "{value}"' for label, value in contact]
    asks_linkedin = any(re.search(r"linkedin", q["label"], re.I) for q in questions)
    for q in questions:
        label = q["label"].strip()
        if asks_linkedin and LINK_FIELD.search(label):
            answers.append(f'{label} = "{DEVPOST}"')
            continue
        if not autofill and label.startswith("LinkedIn Profile"):
            answers.append(f'{label} = "{CONTACT[5][1]}"')
            continue
        if label in STANDARD:
            continue
        want = expected(label)
        if want:
            answers.append(f'{label} = "{want}"')
        elif re.search(LEAVE_BLANK, label, re.I):
            blank.append(label)
        elif q["required"]:
            unknown.append(label)
            blank.append(label)
    start = (
        "Do not click the top \"Apply\" button; scroll down to the form and click the \"Autofill my application\" "
        "button. Then answer"
        if autofill
        else "The resume is already attached; leave the Resume/CV and Cover Letter fields alone. Some fields may "
        "already be filled from the saved profile; leave those if they match. For Phone, choose United States (+1) "
        "as the country first."
        + (" For Location (City), type the city and pick the matching suggestion." if posting.get("location_questions")
           else "")
        + " Answer"
    )
    goal = (
        "Fill this job application without submitting it. " + start + " these questions, top to bottom: "
        + "; ".join(f"{i}) {a}" for i, a in enumerate(answers, 1))
        + ". For a dropdown, open it and click the exact option."
        + (" Leave these blank: " + "; ".join(f'"{b[:90]}"' for b in blank) + "." if blank else "")
        + " Never touch the Voluntary Self-Identification section (Gender, Hispanic/Latino, Race, Veteran,"
        " Disability), file uploads, or any other field. Never click Submit application. Choose DONE when every"
        " question above shows its answer."
    )
    return goal, unknown


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--no-autofill"]
    if len(args) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(*args, autofill="--no-autofill" not in sys.argv))
