"""Finish prepared Greenhouse forms in each run's own tab: answer the user's own fields, then (optionally) submit.

uv run python scripts/jev_finish.py RUN_DIR [RUN_DIR ...] [--set 'LABEL REGEX=OPTION' ...] [--tick 'LABEL REGEX'] [--submit]

--set    answer a dropdown (or text field) whose label matches the regex, e.g. --set 'text message=Yes'
--tick   tick every checkbox in the group whose label matches the regex (e.g. a privacy-notice "I Accept")
--autofill click "Autofill my application" first (when Jev skipped it and contact fields are empty)
--submit click "Submit application" after every field in goal.txt still checks out, then report the page that
         follows (confirmation, validation errors, or a CAPTCHA, which is never solved: the run is left for the user)

Only for answers and agreements the user has given in chat. Each run's tab is found exactly like
jev_check_runs.py does (new since tabs_before.json and showing this job); no other tab is touched.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from browser_harness.admin import ensure_daemon
from browser_harness.helpers import cdp

from jev_check_runs import READ, check

FIND = r"""((pattern, kind) => {
  const re = new RegExp(pattern, 'i');
  const text = e => (e?.innerText || e?.textContent || '').replace(/\s+/g, ' ').trim();
  const labelOf = e => text(document.getElementById(e.getAttribute('aria-labelledby') || '')) ||
    e.getAttribute('aria-label') || text(e.labels?.[0]) || '';
  const box = e => { e.scrollIntoView({block: 'center'}); const r = e.getBoundingClientRect();
    return {x: r.x + r.width / 2, y: r.y + r.height / 2}; };
  if (kind === 'field') {
    const e = [...document.querySelectorAll('input:not([type=hidden]):not([type=file]),textarea')]
      .find(e => !['checkbox', 'radio'].includes(e.type) && re.test(labelOf(e)));
    return e ? {...box(e), combobox: e.getAttribute('role') === 'combobox', id: e.id} : null;
  }
  if (kind === 'checkboxes') {
    for (const g of document.querySelectorAll('fieldset,[role=group]')) {
      const label = text(g.querySelector('legend')) || labelOf(g);
      if (!re.test(label)) continue;
      return [...g.querySelectorAll('input[type=checkbox]')].filter(b => !b.checked).map(b => b.id);
    }
    return null;
  }
})"""

# Options of the dropdown this input controls only: the phone country picker keeps its own (hidden) option list in
# the page, and matching page-wide picked that list instead (Stripe/Affirm/ZipRecruiter, 2026-10-14).
OPTIONS = r"""(id => {
  const input = document.getElementById(id);
  const list = document.getElementById(input?.getAttribute('aria-controls') || input?.getAttribute('aria-owns') || '');
  const all = [...(list || document).querySelectorAll('[role=option]')];
  return list ? all : all.filter(o => o.offsetParent !== null);
})"""

OPTION = r"""((want, id) => {
  const o = (""" + OPTIONS + r""")(id).find(o => o.innerText.trim() === want);
  if (!o) return null;
  o.scrollIntoView({block: 'nearest'}); const r = o.getBoundingClientRect();
  return {x: r.x + r.width / 2, y: r.y + r.height / 2};
})"""


class Tab:
    def __init__(self, target):
        self.session = cdp("Target.attachToTarget", targetId=target, flatten=True)["sessionId"]

    def js(self, expression):
        out = cdp("Runtime.evaluate", session_id=self.session, expression=expression, returnByValue=True,
                  awaitPromise=True)
        return out["result"].get("value")

    def click(self, point):
        for kind in ("mousePressed", "mouseReleased"):
            cdp("Input.dispatchMouseEvent", session_id=self.session, type=kind, x=point["x"], y=point["y"],
                button="left", clickCount=1)
        time.sleep(0.4)

    def find(self, pattern, kind):
        return self.js(f"{FIND}({json.dumps(pattern)}, {json.dumps(kind)})")

    def set(self, pattern, value):
        # A dropdown left open (e.g. the phone country picker) would swallow the clicks below.
        cdp("Input.dispatchKeyEvent", session_id=self.session, type="keyDown", key="Escape")
        time.sleep(0.3)
        field = self.find(pattern, "field")
        if not field:
            return f"no field matching {pattern!r}"
        self.click(field)
        if field["combobox"]:
            cdp("Input.insertText", session_id=self.session, text=value)
            time.sleep(0.6)
            option = self.js(f"{OPTION}({json.dumps(value)}, {json.dumps(field['id'])})")
            if not option:
                offered = self.js(f"({OPTIONS})({json.dumps(field['id'])}).map(o => o.innerText.trim())")
                cdp("Input.dispatchKeyEvent", session_id=self.session, type="keyDown", key="Escape")
                return f"option {value!r} not offered for {pattern!r} (offered: {offered})"
            self.click(option)
        else:
            self.js(f"document.getElementById({json.dumps(field['id'])}).select()")
            cdp("Input.insertText", session_id=self.session, text=value)
        return None

    def autofill(self):
        """Click MyGreenhouse's "Autofill my application" (Jev sometimes skips it) and let it fill."""
        button = self.js(r"""(() => {
          const b = [...document.querySelectorAll('button,a')].find(b => /autofill my application/i.test(b.innerText));
          if (!b) return null; b.scrollIntoView({block: 'center'}); const r = b.getBoundingClientRect();
          return {x: r.x + r.width / 2, y: r.y + r.height / 2};
        })()""")
        if not button:
            return "no Autofill button"
        self.click(button)
        time.sleep(8)
        return None

    def tick(self, pattern):
        ids = self.find(pattern, "checkboxes")
        if ids is None:
            return f"no checkbox group matching {pattern!r}"
        for box_id in ids:
            self.js(f"document.getElementById({json.dumps(box_id)}).click()")
        return None

    def submit(self):
        cdp("Input.dispatchKeyEvent", session_id=self.session, type="keyDown", key="Escape")
        time.sleep(0.5)
        before = self.js("location.href")
        find = r"""(() => {
          const b = [...document.querySelectorAll('button,input[type=submit]')]
            .find(b => /submit application|^submit$/i.test((b.innerText || b.value || '').trim()));
          if (!b || b.disabled) return null; b.scrollIntoView({block: 'center'}); const r = b.getBoundingClientRect();
          return {x: r.x + r.width / 2, y: r.y + r.height / 2};
        })()"""
        button = self.js(find)
        if not button:
            return "no Submit button"
        self.click(button)
        for _ in range(90):
            time.sleep(0.5)
            if _ == 30 and self.js("location.href") == before:
                # The first click after editing a field is sometimes swallowed (seen on C3 AI and Glean). Click once
                # more only if the button is still enabled: a disabled one means the first submit is in progress.
                again = self.js(find)
                if again:
                    self.click(again)
            state = self.js(r"""(() => ({
              url: location.href,
              thanks: /thank you for applying|application (has been )?(received|submitted)|we.ve received/i
                .test(document.body.innerText),
              emailCode: /verification code was sent/i.test(document.body.innerText),
              captcha: [...document.querySelectorAll('iframe')].some(f => /recaptcha|hcaptcha|turnstile/.test(f.src)
                && f.getBoundingClientRect().height > 100),
              errors: [...document.querySelectorAll('[class*=error],[role=alert]')].map(e => e.innerText.trim())
                .filter(Boolean).slice(0, 5)
            }))()""")
            if state["thanks"] or state["url"] != before:
                return "submitted" + ("" if state["thanks"] else f" (now at {state['url']})")
            if state["emailCode"]:
                return "email verification code requested: left for the user"
            if state["captcha"]:
                return "CAPTCHA shown: left for the user"
            if state["errors"] and _ > 6:
                return "not submitted: " + "; ".join(state["errors"])
        return "no confirmation after 45 s: check the tab"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--set", action="append", default=[])
    parser.add_argument("--tick", action="append", default=[])
    parser.add_argument("--autofill", action="store_true", help="Click 'Autofill my application' first.")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--state", action="store_true", help="Only print the page's URL, iframes and notices.")
    parser.add_argument("--show", help="Only print the current value of fields whose label matches this regex.")
    args = parser.parse_args()
    ensure_daemon()
    bad = False
    for run in map(Path, args.runs):
        meta = json.loads((run / "meta.json").read_text())
        before = set(json.loads((run / "tabs_before.json").read_text()))
        pages = [t for t in cdp("Target.getTargets")["targetInfos"] if t["type"] == "page"]
        tabs = [t for t in pages if t["targetId"] not in before and meta["job_id"] in t["url"]]
        if len(tabs) != 1:
            print(f"[SKIP] {meta['job_id']} {meta['title'][:50]}: expected this run's 1 tab, found {len(tabs)}")
            bad = True
            continue
        tab = Tab(tabs[0]["targetId"])
        if args.state:
            print(f"[STATE] {meta['job_id']}: " + json.dumps(tab.js(r"""(() => ({
              url: location.href,
              buttons: [...document.querySelectorAll('button,input[type=submit]')].map(b => (b.innerText || b.value || '')
                .trim() + (b.disabled ? ' [disabled]' : '')).filter(t => /submit/i.test(t)),
              iframes: [...document.querySelectorAll('iframe')].map(f => (f.src || '').slice(0, 80) + ' h=' +
                Math.round(f.getBoundingClientRect().height)).filter(s => !/^ h=0$/.test(s)),
              notes: document.body.innerText.split('\n').map(s => s.trim())
                .filter(s => s.length < 300 && /error|verif|code|captcha|thank|submitted|received|invalid|security/i.test(s))
                .slice(0, 12)
            }))()""")))
            continue
        if args.show:
            fields = tab.js(f"{READ}")["fields"]
            print(f"[SHOW] {meta['job_id']}: " + "; ".join(f"{l[:45]} = {v!r}" for l, v in fields
                                                         if re.search(args.show, l, re.I)))
            continue
        problems = [p for p in [tab.autofill() if args.autofill else None] if p]
        problems += [p for p in (tab.set(*s.split("=", 1)) for s in args.set) if p]
        problems += [p for p in (tab.tick(t) for t in args.tick) if p]
        report = check(run, pages)
        problems += report["problems"]
        if problems:
            print(f"[CHECK] {meta['job_id']} {meta['title'][:50]}: " + "; ".join(problems))
            bad = True
            continue
        outcome = tab.submit() if args.submit else "filled, not submitted"
        bad |= not outcome.startswith("submitted") and args.submit
        print(f"[{'DONE' if outcome.startswith('submitted') else 'READY' if not args.submit else 'CHECK'}] "
              f"{meta['job_id']} {meta['title'][:50]}: {outcome}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
