"""Benchmark Jev on Greenhouse application forms without ever submitting them.

python scripts/jev_bench.py <greenhouse job id> [...] [--board andurilindustries] [--label NAME]

Each form runs through jev_task.py --step. Instead of a person approving each decision, a strict
reviewer approves only: scrolling/waiting/jumping to an empty field, DONE/BLOCKED, the Autofill button,
opening a known question, the expected option for the question just opened, and typing that answer.
Anything else (Submit, self-identification, an unknown question, a wrong option) stops the run.
Afterwards it reads every required field's final answer from the page and scores it.

Writes artifacts/bench/<label>/<job id>.jsonl (the run log) and prints one summary row per form.
"""

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Question label pattern -> expected answer. Order matters: first match wins.
ANSWERS = [
    # Cloudflare (2026-10-13). Free-text "How did you hear" must precede the Databricks entry.
    (r"How did you hear about this job\?$", "Careers site"),
    (r"acknowledge Cloudflare's Candidate Privacy Policy", "Acknowledge/Confirm"),
    (r"currently reside in the Austin, TX metro area", "No, but I am willing to relocate within 6 months of employment"),
    (r"currently based in Austin, London or Lisbon", "No"),
    (r"not based in Austin, London, or Lisbon, are you willing to relocate", "Yes"),
    (r"based at our Austin,TX office", "Yes"),
    (r"include your LinkedIn profile, personal website or blog", "https://www.linkedin.com/in/alex-sample"),
    # ZipRecruiter / Roku (2026-10-14)
    (r"archetype are you most closely aligned with", "Machine Learning"),
    (r"What school are you currently attending", "Example University"),
    (r"When is your anticipated graduation date", "[your answer]"),
    (r"open to relocation to Santa Monica", "Yes"),
    (r"How did you hear about this opportunity\?", "ZipRecruiter.com"),
    (r"authorized to lawfully work for Roku", "Yes"),
    # Formlabs / xAI (2026-10-14). Essays drafted by Claude from the user's facts; user edited wording.
    (r"legally eligible to work in the United States for Formlabs", "Yes"),
    (r"require visa sponsorship for employment at Formlabs", "No"),
    (r"Describe a technical question you needed to answer through testing", "[your answer]"),
    (r"^Website/Portfolio", "https://devpost.com/alexsample"),
    (r"How did you hear about us\?$", "Google"),
    (r"^Full Legal Name in Native Language", "Alex Van Sample"),
    (r"^Full Legal Name", "Alex Van Sample"),
    (r"^Current company", "Example University"),
    (r"^Current title", "Research Assistant"),
    (r"^Your Location", "Springfield, FL"),
    (r"If working in the US, will you now, or in the future, require sponsorship", "No"),
    (r"indicate your SpaceXSI employment history", "I have never worked for SpaceXSI, SpaceX, SpaceXAI, xAI, X, or Twitter"),
    (r"What exceptional work have you done", "[your answer]"),
    # New-grad batch (2026-10-13): Stripe, Pinterest, Nuro, Affirm, SpaceX. Preferences chosen by Claude, told to user.
    (r"Do you require visa sponsorship, now or in the future", "No, I do not require visa sponsorship now or in the future to continue working in the country where this role is based."),
    (r"^LinkedIn Profile, Github, Personal Website, or Portfolio", "https://www.linkedin.com/in/alex-sample"),
    (r"active offer deadline or another recruiting-process deadline", "No"),
    (r"When are you available to start full-time\?", "[your answer]"),
    (r"currently eligible to work in the United States\?", "Yes, I am currently eligible to work in the country where this role is based."),
    (r"first location preference|^Second location preference|^Third location preference", "I am open to working in any office"),
    (r"top 3 engineer profile types", "Backend"),
    (r"^Second engineering preference", "Infrastructure / Systems Design"),
    (r"^Third engineering preference", "Security Engineering"),
    (r"current or previous employer\?", "Example University"),
    (r"current or previous job title\?", "Research Assistant"),
    (r"in what city and state do you reside", "Springfield, FL"),
    (r"select the country where you currently reside", "US"),
    (r"What U\.S State do you currently reside in|U\.S\. State or Canadian Province do you reside in", "Florida"),
    (r"able to start between January 2027 and September 2027", "[your answer]"),
    (r"By June 2027, will you obtain your Bachelor", "[your answer]"),
    (r"roles may be remote or hybrid depending on team", "Yes"),
    (r"currently pursuing a Bachelor's or Master's degree", "Bachelor's"),
    (r"What type of engineering are you primarily interested in", "Backend"),
    (r"What is your preferred office location\?", "San Francisco"),
    (r"authorized to work in the country in which you are applying", "Yes"),
    (r"4 days a week in office, including Thursdays in our Mountain View", "Yes"),
    (r"^Preferred Name", "Alex"),
    (r"^Pronouns", "[your answer]"),
    (r"first learn about Affirm as an employer", "Affirm’s Career Site"),
    (r"previously been employed at Affirm", "I have not previously been employed at Affirm"),
    (r"^Active Security Clearance", "[your answer]"),
    (r"SpaceX & SpaceXAI Employment History", "I have never worked for SpaceX, SpaceXAI, xAI, X, or Twitter"),
    (r"perform all of the essential functions of this role", "Yes"),
    (r"^Are you legally authorized to work in the United States\?", "I am authorized to work in the United States for any employer"),
    (r"^Citizenship Status", "[your answer]"),
    (r"^GPA \(Graduate\)", "Other/Not Applicable"),
    (r"^GPA \(Doctorate\)", "Not applicable/Do not recall"),
    (r"^GRE Score", "Did not take/Do not recall"),
    (r"^ACT Score", "[your answer]"),
    (r"^SAT Score", "Did not take/Do not recall"),
    (r"^GPA \(Undergraduate\)", "Not applicable/Do not recall"),  # user chose "do not recall"
    # Abnormal Security (2026-10-13). Zip and current company given by the user.
    (r"25% in office in San Francisco. Are you currently located in the Bay Area", "No"),
    (r"preferred Last Name/Surname", "Van Sample"),
    (r"^Zip Code/Postal Code", "32000"),
    (r"^Current Company", "Example University"),
    (r"currently an employee or contractor at Abnormal", "No"),
    (r"previously worked at Abnormal", "No"),
    (r"eligible to work in the country in which this job is posted", "Yes"),
    (r"immigration related support or sponsorship", "No"),
    (r"^LinkedIn Profile", "https://www.linkedin.com/in/alex-sample"),
    # Roblox / Scale AI / Anduril (2026-10-12). Arbitration agreements stay the user's own (LEAVE_BLANK): forms that
    # require one are held back for the user.
    (r"require sponsorship", "No"),  # before WORK AUTHORIZATION, which also matches "...for work authorization"
    (r"^Legal Name", "Alex Van Sample"),
    (r"18\+ years of age", "Yes"),
    (r"available to work as a full-time, permanent employee", "[your answer]"),
    (r"preferred coding language", "Python 3"),
    (r"How did you first hear about this role", "Roblox Careers Site"),
    (r"hybrid schedule \(3\+ days in office\) at our San Mateo", "Yes"),
    (r"acknowledge Roblox's Job Applicant Privacy Notice",
     "I acknowledge that I have read and understood Roblox's Job Applicant Privacy Notice."),
    (r"graduation date will be either Fall 2026 or Spring 2027", "[your answer]"),
    (r"not local to Colorado, are you willing to relocate", "Yes"),
    # Arize AI (2026-10-11). Pronouns are optional and the user's own: left blank.
    (r"based in the S(an )?F(rancisco)? Bay", "No"),
    (r"^Github URL", "https://github.com/alexsample"),
    (r"legally authorized to work in the US", "Yes"),
    # Glean (2026-10-11).
    (r"commit to the hybrid policy", "Yes"),
    (r"know anyone (currently )?(at|who works)|friends or family (who )?work", "No"),  # user: assume no contacts anywhere
    (r"How did you hear about Glean", "Glean Career Site"),
    (r"total years of experience you have that are relevant", "2"),
    (r"What AI tools are you currently using", "[your answer]"),
    # C3 AI (2026-10-11). The privacy-notice "I Accept", SMS consent and highest completed education are the
    # user's own: see LEAVE_BLANK.
    (r"work from our Headquarters in Redwood City|work from our Redwood City, CA office|work onsite from our HQ"
     r"|work 5x week from one of the offices", "Yes"),
    (r"expected graduation month and year", "[your answer]"),
    (r"How did you hear about C3 AI", "C3 AI Website"),
    (r"commuting distance of C3 AI", "No"),
    (r"sponsor you for a visa", "No"),
    (r"Which office location do you prefer", "Redwood City, CA"),
    (r"years of professional software development experience do you have", "Less than 2 years"),
    (r"^Are you a U\.S\. citizen", "[your answer]"),
    (r"^Where are you currently located", "Springfield, Florida, United States"),
    # Anthropic (2026-10-11). "Why Anthropic?", the AI-policy attestation and the arbitration agreement are the
    # user's own (Anthropic's candidate AI guidance; a legal waiver): see LEAVE_BLANK.
    (r"open to working in-person in one of our offices", "Yes"),
    (r"open to relocation for this role", "Yes"),
    (r"interviewed at Anthropic before", "No"),
    (r"address from which you plan on working", "relocating"),
    (r"^Publications", "[your answer]"),
    # Figma (2026-10-11). The essay was approved by the user.
    (r"^Why do you want to join Figma\?", "[your answer]"),
    (r"From where do you intend to work", "Open to either San Francisco or New York"),
    (r"best describes your primary technical expertise", "ML/AI, Full-Stack"),
    (r"programming languages do you regularly use", "C++, Python"),
    (r"authorized to work in the country for which you applied", "Yes"),
    (r"ever worked for Figma", "No"),
    (r"How many years of professional experience", "0–2 years"),
    (r"worked as a full-time software engineer", "No"),
    (r"expected graduation date", "[your answer]"),
    (r"able to work from Figma.s NYC or SF Hub", "Yes"),
    (r"How did you connect with us", "Other"),
    # Databricks (2026-10-11)
    (r"legally authorized to work", "Yes"),
    (r"worked for Databricks", "No"),
    (r"Please confirm whether any of the below applies", "None of the above"),  # sanctions; must precede EXPORT CONTROLS
    (r"If you selected a response to the prior question", "[your answer]"),
    (r"requires U\.S\. ci", "Yes"),
    (r"Preferred First Name", "Alex"),
    (r"How did you hear about this job", "Databricks careers website"),
    # Anduril (2026-10-10)
    (r"willing to relocate", "Yes"),
    (r"academic transcripts", "No"),
    (r"CLEARANCE ELIGIBILITY", "[your answer]"),
    (r"held a U\.S\. security clearance in the past", "[your answer]"),
    (r"EXPORT CONTROLS", "[your answer]"),
    (r"WORK AUTHORIZATION", "Yes"),
    (r"sponsorship", "No"),
    (r"U\.S\. Person", "[your answer]"),
    (r"HISTORY WITH ANDURIL|previously applied", "Yes"),
    (r"ever been employed by Anduril", "No"),
    (r"CONFLICT OF INTEREST", "No"),
    (r"top location preference", "Costa Mesa, CA (HQ)"),
    (r"3 months - 2 years", "Yes"),
    (r"How did you hear", "Google job search"),
]
LEAVE_BLANK = (r"country of your birth|countries of which you are a citizen|lawful permanent resident"
               r"|^Why Anthropic|AI Policy for Application|arbitration agreement|Agreement to Arbitrate"
               r"|Applicant & Candidate Privacy Notice|consent to receiving follow up communication via text"
               r"|highest level of education you have completed|If you do require employee sponsorship")
AUTOFILLED = {"First Name", "Last Name", "Email", "Phone", "Country"}

GOAL = (
    "Fill this job application without submitting it. Do not click the top \"Apply\" button; scroll down to the "
    "form and click the \"Autofill my application\" button. Then answer every one of these questions that exists "
    "on this form, top to bottom: "
    + "; ".join(f'{pattern.split("|")[0].replace(chr(92), "")} = "{answer}"' for pattern, answer in ANSWERS)
    + ". For \"How did you hear\", select the \"Google job search\" option. Leave the country-of-birth, "
    "citizenship-countries and permanent-residence text questions blank. Never touch the Voluntary "
    "Self-Identification section (Gender, Hispanic/Latino, Race, Veteran, Disability), file uploads, or any "
    "other field. Never click Submit application. Choose DONE when every listed question that exists shows its answer."
)

SAFE_OPERATIONS = {"SCROLL_DOWN", "SCROLL_UP", "WAIT", "NEXT_EMPTY_FIELD", "DONE", "BLOCKED"}


def expected(label):
    return next((answer for pattern, answer in ANSWERS if re.search(pattern, label or "", re.I)), None)


class Reviewer:
    """Approves a decision only if it is one of the allowed moves; remembers the dropdown just opened."""

    def __init__(self):
        self.open_question = None

    def review(self, decision):
        operation, element = decision["operation"], decision.get("element") or ""
        if operation in SAFE_OPERATIONS:
            return True, None
        if re.search(r"submit|apply for this job|^apply$", element, re.I):
            return False, f"refused {operation} on {element!r}"
        if operation == "CLICK" and element == "Autofill my application":
            return True, None
        if operation == "CLICK" and expected(element):
            self.open_question = element
            return True, None
        if operation == "CLICK" and self.open_question and element == expected(self.open_question):
            return True, None  # Forget the question only once the option executes: a stale retry repeats it.
        if operation == "TYPE_TEXT" and re.search(r"How did you hear", element, re.I):
            self.open_question = element
            return True, None
        return False, f"not allowed: {operation} {element[:80]!r} (open question: {(self.open_question or '')[:50]!r})"

    def executed(self, action):
        if self.open_question and action.get("action") == expected(self.open_question):
            self.open_question = None


def page_tabs():
    """IDs of every open Chrome tab, taken before a run so its own new tab can be told apart."""
    code = r"""
import json
from browser_harness.admin import ensure_daemon
from browser_harness.helpers import cdp
ensure_daemon()
print(json.dumps([t["targetId"] for t in cdp("Target.getTargets")["targetInfos"] if t["type"] == "page"]))
"""
    out = subprocess.run(["uv", "run", "python", "-c", code], cwd=ROOT, capture_output=True, text=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def read_answers(job_url, before):
    """Final value of every required field on this run's own tab, then close that tab.

    Only a tab that is new since the run started and shows this form qualifies; any other tab
    (including the user's own copies of the same form) is never read or closed.
    """
    code = r"""
import json, sys
from browser_harness.admin import ensure_daemon
from browser_harness.helpers import cdp
ensure_daemon()
url, before = sys.argv[1], set(json.loads(sys.argv[2]))
tabs = [t for t in cdp("Target.getTargets")["targetInfos"]
        if t["type"] == "page" and t["targetId"] not in before and t["url"].startswith(url)]
if len(tabs) != 1:
    print(json.dumps({"error": f"expected this run's 1 new tab, found {len(tabs)}"})); raise SystemExit
tab = tabs[0]
session = cdp("Target.attachToTarget", targetId=tab["targetId"], flatten=True)["sessionId"]
js = r'''(() => [...document.querySelectorAll('input[aria-required=true],textarea[aria-required=true]')].map(e => {
  const label = (document.getElementById(e.getAttribute('aria-labelledby') || '')?.innerText
    || e.labels?.[0]?.innerText || e.id).replace(/\s+/g, ' ').replace(/\s*\*\s*$/, '').trim();
  let value = e.value;
  if (e.getAttribute('role') === 'combobox') {
    const control = e.closest('[class*="control"]') || e.parentElement?.parentElement;
    value = control?.querySelector('[class*="single-value"]')?.innerText?.trim() || '';
  }
  return [label, value];
}))()'''
values = cdp("Runtime.evaluate", session_id=session, expression=js, returnByValue=True)["result"]["value"]
cdp("Target.closeTarget", targetId=tab["targetId"])
print(json.dumps({"values": values}))
"""
    out = subprocess.run(
        ["uv", "run", "python", "-c", code, job_url, json.dumps(before)], cwd=ROOT, capture_output=True, text=True
    )
    lines = out.stdout.strip().splitlines()
    answer = json.loads(lines[-1]) if lines else {"error": out.stderr.strip()[-300:]}
    if "error" in answer:
        raise RuntimeError(f"Could not read this run's form: {answer['error']}")
    return answer["values"]


def score(values):
    right, wrong, missing = [], [], []
    for label, value in values or []:
        want = expected(label)
        if want is None:
            # Autofilled (contact, education) or deliberately blank fields have no expected answer.
            # Only an empty field nobody planned for is a problem.
            if value or label in AUTOFILLED or re.search(LEAVE_BLANK, label, re.I):
                continue
            want = "(unplanned required field)"
        (right if value == want else missing if not value else wrong).append((label[:50], value, want))
    return right, wrong, missing


def run(job_id, board, folder):
    url = f"https://job-boards.greenhouse.io/{board}/jobs/{job_id}"
    output = folder / f"run_{job_id}"
    output.mkdir(parents=True, exist_ok=True)
    for stale in ("control", "log.jsonl", "result.json", "requests.jsonl"):
        (output / stale).unlink(missing_ok=True)
    before = page_tabs()
    process = subprocess.Popen(
        ["uv", "run", "--env-file", ".env", "python", "scripts/jev_task.py", "--step", "--keep-open",
         "--max-steps", "70", "--timeout", "120", "--output", str(output), "--url", url, "--goal", GOAL],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        env={**os.environ, "JEV_SAVE_REQUESTS": "1"},
    )
    log, reviewer, seen, stop_reason, started = output / "log.jsonl", Reviewer(), 0, None, time.monotonic()
    while process.poll() is None:
        lines = log.read_text().splitlines() if log.exists() else []
        for line in lines[seen:]:
            seen += 1
            event = json.loads(line)
            if event["event"] == "action":
                reviewer.executed(event)
            if event["event"] != "decision":
                continue
            ok, reason = reviewer.review(event)
            if not ok:
                stop_reason = reason
            (output / "control").write_text("go" if ok else "stop")
        time.sleep(0.1)
    events = [json.loads(line) for line in log.read_text().splitlines() if line.startswith("{")]
    (folder / f"{job_id}.jsonl").write_text(log.read_text())
    decisions = [e for e in events if e["event"] == "decision"]
    result = next((e for e in reversed(events) if e["event"] == "result"), {})
    right, wrong, missing = score(read_answers(url, before))
    confidences = [d["confidence"] for d in decisions]
    return {
        "job": job_id,
        "outcome": result.get("outcome"),
        "stop": stop_reason or result.get("error"),
        "actions": result.get("steps"),
        "decisions": len(decisions),
        "mean_conf": round(statistics.mean(confidences), 3) if confidences else None,
        "min_conf": min(confidences) if confidences else None,
        "low_conf(<0.5)": sum(c < 0.5 for c in confidences),
        "correct": len(right),
        "wrong": wrong,
        "missing": missing,
        "seconds": round(time.monotonic() - started),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("jobs", nargs="+")
    parser.add_argument("--board", default="andurilindustries")
    parser.add_argument("--label", default=time.strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    folder = ROOT / "artifacts" / "bench" / args.label
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for job in args.jobs:
        row = run(job, args.board, folder)
        rows.append(row)
        print(json.dumps(row), flush=True)
    (folder / "summary.json").write_text(json.dumps(rows, indent=1))
    confidences = [r["mean_conf"] for r in rows if r["mean_conf"] is not None]
    print(json.dumps({
        "label": args.label,
        "forms": len(rows),
        "mean_conf": round(statistics.mean(confidences), 3) if confidences else None,
        "correct": sum(r["correct"] for r in rows),
        "wrong": sum(len(r["wrong"]) for r in rows),
        "missing": sum(len(r["missing"]) for r in rows),
        "done": sum(r["outcome"] == "done" for r in rows),
    }))


if __name__ == "__main__":
    sys.exit(main())
