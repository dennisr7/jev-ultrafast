"""Read-only check of a Greenhouse form that Jev filled. Never clicks, types, navigates, or closes anything.

uv run python scripts/jev_read_form.py snapshot OUT.json   # before starting Jev: record the open tab IDs
uv run python scripts/jev_read_form.py read URL OUT.json   # after the run: read Jev's new tab on URL

`read` picks the one tab that is new since `snapshot` and shows URL (never another tab, such as the user's own copy
of the same form), then prints every required field's current value as JSON: dropdowns as their chosen option,
typed fields as "(filled)" or "" (personal details are not printed), plus the resume file name.
"""

import json
import sys

from browser_harness.admin import ensure_daemon
from browser_harness.helpers import cdp

READ = r"""(() => {
  const fields = [...document.querySelectorAll('input[aria-required=true],textarea[aria-required=true]')].map(e => {
    const label = (document.getElementById(e.getAttribute('aria-labelledby') || '')?.innerText
      || e.labels?.[0]?.innerText || e.id).replace(/\s+/g, ' ').replace(/\s*\*\s*$/, '').trim();
    if (e.getAttribute('role') === 'combobox') {
      const control = e.closest('[class*="control"]') || e.parentElement?.parentElement;
      return [label, control?.querySelector('[class*="single-value"]')?.innerText?.trim() || ''];
    }
    return [label, e.value.trim() ? '(filled)' : ''];
  });
  const resume = [...document.querySelectorAll('div')]
    .find(d => /^Resume\/CV/.test(d.innerText || '') && d.innerText.length < 200)?.innerText.replace(/\s+/g, ' ');
  return {fields, resume};
})()"""


def pages():
    return [t for t in cdp("Target.getTargets")["targetInfos"] if t["type"] == "page"]


def main(argv):
    ensure_daemon()
    if len(argv) == 2 and argv[0] == "snapshot":
        json.dump([t["targetId"] for t in pages()], open(argv[1], "w"))
        print(json.dumps({"recorded_tabs": len(pages())}))
        return 0
    if len(argv) == 3 and argv[0] == "read":
        url, before = argv[1].rstrip("/"), set(json.load(open(argv[2])))
        tabs = [t for t in pages() if t["targetId"] not in before and t["url"].rstrip("/").startswith(url)]
        if len(tabs) != 1:
            print(json.dumps({"error": f"expected exactly 1 new tab on this form, found {len(tabs)}"}))
            return 1
        session = cdp("Target.attachToTarget", targetId=tabs[0]["targetId"], flatten=True)["sessionId"]
        value = cdp("Runtime.evaluate", session_id=session, expression=READ, returnByValue=True)["result"]["value"]
        print(json.dumps(value, indent=1))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
