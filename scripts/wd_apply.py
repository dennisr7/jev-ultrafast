"""Fill a Workday application through its stable data-automation-id hooks (2026-10-16, reworked 2026-10-24).

uv run python scripts/wd_apply.py --url <job posting URL> [--accept-terms] [--max-pages 12]
uv run python scripts/wd_apply.py --tab <targetId prefix | url substring> [--start] [--accept-terms]
  --url           open a new tab on the posting, then --start in it.
  --start         from the job or /apply page: Autofill with Resume, attach the resume, continue to My Information.
                  At a sign-in page it stops (exit 5): signing in and creating accounts are the applicant's, never the script's.
  --accept-terms  tick Workday's own Terms box (only when the applicant said to); other attestations are never ticked.

Mechanics are scripted; decisions are not. Each page settles, gets filled from scripts/wd_answers.json, and every
answer is read back; the page is saved only if all of them still read back (going Back later makes Workday drop
saved job panels). Questions with no stored answer stop the run and go to artifacts/workday/<tenant>/pending.json
with their real options; Claude (or the applicant) answers them with scripts/wd_answer.py, then the run is repeated.
It never clicks Submit. At Review it checks each job, the education block and every known answer.
Exit codes: 0 Review checked OK, 3 questions pending (decide/yours), 4 stuck or Review check failed, 5 cannot start
(no Google sign-in, posting gone, already applied), 2 usage.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from browser_harness.admin import ensure_daemon
from browser_harness.helpers import cdp
from profile_guard import require_primary

ROOT = Path(__file__).resolve().parents[1]
RESUME = ROOT.parent / "cv" / "Alex Van Sample.pdf"
UPLOAD = ROOT / "artifacts" / "workday" / "Alex Van Sample Resume.pdf"  # some tenants require "Resume"/"CV" in the name
ANSWERS = json.loads((ROOT / "scripts" / "wd_answers.json").read_text())


class Tab:
    def __init__(self, ref):
        pages = [t for t in cdp("Target.getTargets")["targetInfos"] if t["type"] == "page"]
        hits = [t for t in pages if t["targetId"].startswith(ref) or ref in t["url"]]
        if not hits:
            sys.exit(f"no tab matching {ref!r}")
        self.target = hits[0]["targetId"]
        self.s = cdp("Target.attachToTarget", targetId=self.target, flatten=True)["sessionId"]

    def js(self, expr):
        r = cdp("Runtime.evaluate", session_id=self.s, expression=expr, returnByValue=True, awaitPromise=True)
        return r["result"].get("value")

    def click(self, p):
        if not p:
            return False
        for k in ("mousePressed", "mouseReleased"):
            cdp("Input.dispatchMouseEvent", session_id=self.s, type=k, x=p["x"], y=p["y"], button="left", clickCount=1)
        time.sleep(0.5)
        return True

    def key(self, name, code, vk):
        for k in ("keyDown", "keyUp"):
            cdp("Input.dispatchKeyEvent", session_id=self.s, type=k, key=name, code=code, windowsVirtualKeyCode=vk)
        time.sleep(0.3)

    def type(self, text):
        cdp("Input.insertText", session_id=self.s, text=text)
        time.sleep(0.4)

    def point(self, selector_js):
        """Center of the element the JS expression returns, scrolled to the middle (clear of the sticky footer)."""
        return self.js(f"""(()=>{{const e={selector_js}; if(!e) return null; e.scrollIntoView({{block:'center'}});
            const r=e.getBoundingClientRect(); return {{x:r.x+r.width/2, y:r.y+r.height/2}}}})()""")


FIELDS_JS = r"""(() => {
  const out = [];
  for (const f of document.querySelectorAll('[data-automation-id^="formField-"]')) {
    if (!f.offsetParent) continue;
    const key = f.getAttribute('data-automation-id').slice(10);
    const label = (f.querySelector('label,legend')?.innerText || '').replace(/\s+/g, ' ').trim();
    const required = /\*\s*$/.test(label) || !!f.querySelector('[aria-required=true],[required]');
    let type = 'text', value = '';
    const sel = f.querySelector('button[aria-haspopup=listbox]');
    const radios = [...f.querySelectorAll('input[type=radio]')];
    const boxes = [...f.querySelectorAll('input[type=checkbox]')];
    const multi = f.querySelector('[data-automation-id=multiselectInputContainer], [data-automation-id=selectedItemList]');
    const panel = f.closest('[aria-labelledby$="-panel"]')?.getAttribute('aria-labelledby') || '';
    if (f.querySelector('input[type=file]') || /attachments/i.test(f.getAttribute('data-fkit-id') || '')) { type = 'file';
      value = [...f.querySelectorAll('[data-automation-id=file-upload-item-name]')].map(e => e.innerText.trim()).join(', '); }
    else if (sel) { type = 'select'; value = sel.innerText.trim(); if (/^select one$/i.test(value)) value = ''; }
    else if (radios.length) { type = 'radio'; const c = radios.find(r => r.checked);
      value = c ? (document.querySelector(`label[for="${c.id}"]`)?.innerText || c.value).trim() : ''; }
    else if (f.querySelector('[data-automation-id=dateSectionYear-input]')) { type = 'date';
      const m = f.querySelector('[data-automation-id=dateSectionMonth-input]'), y = f.querySelector('[data-automation-id=dateSectionYear-input]');
      value = [(m && m.value) ? String(m.value).padStart(2, '0') : '', y.value].filter(Boolean).join('/'); }
    else if (boxes.length > 1 && !multi) { type = 'checkgroup';
      value = boxes.filter(b => b.checked).map(b => (document.querySelector(`label[for="${b.id}"]`)?.innerText || '').trim()).join(', '); }
    else if (boxes.length === 1 && !multi) { type = 'checkbox'; value = boxes[0].checked ? 'yes' : ''; }
    else if (multi) { type = 'prompt';
      value = [...f.querySelectorAll('[data-automation-id=selectedItem]')].map(e => e.innerText.trim()).join(', '); }
    else { const i = f.querySelector('textarea, input:not([type=hidden])'); value = (i?.value || '').trim();
      if (i?.tagName === 'TEXTAREA') type = 'textarea'; }
    out.push({key, label: label.replace(/\*$/, '').trim(), required, type, value, panel});
  }
  const step = document.querySelector('[data-automation-id=progressBarActiveStep]')?.innerText.replace(/\s+/g, ' ') || '';
  const errors = [...document.querySelectorAll('[data-automation-id=errorMessage], [data-automation-id*=error] [role=alert]')]
    .map(e => e.innerText.trim()).filter(Boolean);
  if (/Errors Found/.test(document.body.innerText)) errors.push(...[...document.querySelectorAll('[data-automation-id=errorBanner], [role=alert], li')].map(e => e.innerText.trim()).filter(t => /error/i.test(t)).slice(0, 5));
  if (/Something went wrong/.test(document.body.innerText)) errors.push('Workday error page: "Something went wrong" (session went stale; reload and retry)');
  return {step, fields: out, errors, url: location.pathname};
})()"""


def field_js(key):
    return f'document.querySelector(\'[data-automation-id="formField-{key}"]\')'


TENANT = None
ACCEPT_TERMS = False
PANEL_KEYS = {'jobTitle','companyName','location','currentlyWorkHere','startDate','endDate','roleDescription','schoolName','degree','fieldOfStudy','gradeAverage','firstYearAttended','lastYearAttended','url','linkedInAccount','skills'}


def norm(label):
    return re.sub(r"\s+", " ", label).strip().rstrip("*").strip()


def answer_for(f):
    if f["key"] == "acceptTermsAndAgreements" and ACCEPT_TERMS:
        return "yes"
    decided = ANSWERS.get("by_question", {}).get(TENANT or "", {}).get(norm(f["label"]))
    if decided is not None:
        return decided["value"]
    company = ANSWERS.get("by_company", {}).get(TENANT or "", {})
    if f["key"] in company:
        return company[f["key"]]
    for pattern, value in ANSWERS.get("by_company_label", {}).get(TENANT or "", []):
        if re.search(pattern, f["label"], re.I):
            return value
    if f["key"] in ANSWERS["by_key"]:
        return ANSWERS["by_key"][f["key"]]
    for pattern, value in ANSWERS["by_label"]:
        if re.search(pattern, f["label"], re.I):
            return value
    return None


def dismiss_dialogs(tab):
    """Workday's "Discard Changes?" dialog swallows every click until answered; keep the page's changes."""
    return tab.js("""(()=>{const d=[...document.querySelectorAll('[role=dialog]')].find(d=>d.offsetParent && /discard changes/i.test(d.innerText));
        const b=d && [...d.querySelectorAll('button')].find(b=>b.innerText.trim()==='Continue'); if(b){b.click(); return true} return false})()""")


def field_options(tab, f):
    """The choices a question offers, so whoever decides picks a real option instead of guessing wording."""
    sel = f"document.querySelector('[data-automation-id=\"formField-{f['key']}\"]')"
    if f["type"] in ("radio", "checkgroup"):
        return tab.js(f"""[...{sel}.querySelectorAll('input')].map(i => (document.querySelector(`label[for="${{i.id}}"]`)?.innerText || i.value).trim())""")
    if f["type"] == "select":
        button = f"{sel}?.querySelector('button[aria-haspopup=listbox]')"
        got = []
        for _ in range(3):
            time.sleep(0.5)
            tab.click(tab.point(button))
            got = options(tab) if wait_listbox(tab, button) else []
            tab.key("Escape", "Escape", 27)
            if got:
                break
        return [o for o in dict.fromkeys(got) if o != "Select One" and not re.search(r"\(\+\d+\)$", o)]
    if f["type"] == "prompt":
        tab.click(tab.point(f"{sel}?.querySelector('input')"))
        tab.key("Enter", "Enter", 13)
        time.sleep(1.5)
        got = options(tab)
        tab.key("Escape", "Escape", 27)
        return [o for o in dict.fromkeys(got) if not re.search(r"\(\+\d+\)$", o)] + ["(nested: categories above may contain more)"]
    return None


def write_pending(tab, step, decide, yours, stuck):
    out = ROOT / "artifacts" / "workday" / (TENANT or "unknown") / "pending.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = [dict(kind="decide", label=norm(f["label"]), key=f["key"], type=f["type"], required=f["required"],
                 options=field_options(tab, f)) for f in decide]
    rows += [dict(kind="yours", label=norm(f["label"]), type=f["type"]) for f in yours]
    rows += [dict(kind="stuck", detail=x) for x in stuck]
    out.write_text(json.dumps({"tenant": TENANT, "url": tab.js("location.href"), "step": step, "questions": rows},
                              indent=2, ensure_ascii=False))
    return out


def wait_listbox(tab, button, timeout=4.0):
    """Workday listboxes render slowly; wait until one is open (its button reports aria-expanded)."""
    end = time.time() + timeout
    while time.time() < end:
        if tab.js(f"{button}?.getAttribute('aria-expanded') === 'true' && "
                  "[...document.querySelectorAll('[role=listbox] [role=option]')].some(o => o.offsetParent)"):
            time.sleep(0.3)
            return True
        time.sleep(0.25)
    return False


def options(tab):
    return tab.js("""[...document.querySelectorAll('[role=option], [data-automation-id=promptOption]')]
        .filter(o => o.offsetParent).map(o => o.innerText.trim()).filter(Boolean)""") or []


def click_option(tab, want):
    p = tab.point(f"""[...document.querySelectorAll('[role=option], [data-automation-id=promptOption]')]
        .filter(o => o.offsetParent).find(o => o.innerText.trim().toLowerCase() === {json.dumps(want.lower())})
        || [...document.querySelectorAll('[role=option], [data-automation-id=promptOption]')]
        .filter(o => o.offsetParent).find(o => o.innerText.trim().toLowerCase().startsWith({json.dumps(want.lower())}))
        || [...document.querySelectorAll('[role=option], [data-automation-id=promptOption]')]
        .filter(o => o.offsetParent).find(o => o.innerText.trim().toLowerCase().includes({json.dumps(want.lower())})
        && !/\\bnot\\b|\\bnon[- ]/i.test(o.innerText.replace({json.dumps(want)}, '')))""")
    if p:
        tab.click(p)
        return True
    return False


def prefs(value):
    """An answer is one value or an ordered list of acceptable ones (option lists differ per company)."""
    return value if isinstance(value, list) else [value]


def matches(have, want):
    return any(v.lower() in have.lower() for v in prefs(want))


def set_field(tab, f, value, scope=None):
    k = f["key"]
    field_js = (lambda k: f"{scope}.querySelector('[data-automation-id=\"formField-{k}\"]')") if scope else globals()["field_js"]
    if f["type"] in ("text", "textarea"):
        p = tab.point(f"{field_js(k)}?.querySelector('textarea, input:not([type=hidden])')")
        if not tab.click(p):
            return "field not found on the page (re-rendered?)"
        tab.js("document.activeElement.select && document.activeElement.select()")
        tab.type(value)
        tab.key("Tab", "Tab", 9)
    elif f["type"] == "select":
        button = f"{field_js(k)}?.querySelector('button[aria-haspopup=listbox]')"
        for _ in range(2):  # a click right after the previous selection is sometimes swallowed
            if not tab.click(tab.point(button)):
                return "dropdown not found"
            if wait_listbox(tab, button):
                break
            tab.key("Escape", "Escape", 27)
        if not any(click_option(tab, v) for v in prefs(value)):
            got = options(tab)
            tab.key("Escape", "Escape", 27)
            return f"option {value!r} not offered (offered: {got[:12]})"
    elif f["type"] == "prompt":
        if not tab.click(tab.point(f"{field_js(k)}?.querySelector('input')")):
            return "search field not found"
        for v in prefs(value):  # typing the value finds it directly, however deeply the prompt nests
            tab.js("document.activeElement.select && document.activeElement.select()")
            tab.type(v)
            tab.key("Enter", "Enter", 13)
            time.sleep(1.5)
            if click_option(tab, v) and tab.js(f"!!{field_js(k)}?.querySelector('[data-automation-id=selectedItem]')"):
                break
        else:
            tab.js("document.activeElement.select && document.activeElement.select()")
            tab.key("Backspace", "Backspace", 8)
            tab.key("Enter", "Enter", 13)  # empty search lists the top-level categories
            time.sleep(1.5)
        for _ in range(3 if not tab.js(f"!!{field_js(k)}?.querySelector('[data-automation-id=selectedItem]')") else 0):  # prompts nest (e.g. "Adobe Source" > "Adobe.com"): click a wanted option, else drill in
            if any(click_option(tab, v) for v in prefs(value)):
                if not tab.js(f"!!{field_js(k)}?.querySelector('[data-automation-id=selectedItem]')"):
                    continue  # that click opened a category rather than selecting
                break
            cat = tab.js("""(()=>{const o=[...document.querySelectorAll('[data-automation-id=promptOption]')].filter(o=>o.offsetParent
                && !/\\(\\+\\d+\\)/.test(o.innerText)).map(o=>o.innerText.trim());
                return o.find(t=>/source|career|compan|website|direct|internet|job board|other/i.test(t)) || null})()""")
            if not cat or not click_option(tab, cat):
                break
            time.sleep(1.5)
        if not tab.js(f"!!{field_js(k)}?.querySelector('[data-automation-id=selectedItem]')"):
            got = options(tab)
            tab.key("Escape", "Escape", 27)
            return f"no wanted option in the prompt (offered: {got[:12]})"
        tab.key("Escape", "Escape", 27)
    elif f["type"] == "date":
        return set_date(tab, scope or "document", k, value)
    elif f["type"] == "radio":
        p = tab.point(f"""(()=>{{const r=[...{field_js(k)}.querySelectorAll('input[type=radio]')].find(r =>
            (document.querySelector(`label[for="${{r.id}}"]`)?.innerText || r.value).trim().toLowerCase() === {json.dumps(value.lower())});
            return r}})()""")  # the input itself: some tenants (Adobe) ignore clicks on the label
        if not p:
            return f"radio {value!r} not found"
        tab.click(p)
    elif f["type"] == "checkgroup":
        if matches(f["value"], value):
            return None
        p = tab.point(f"""(()=>{{const b=[...{field_js(k)}.querySelectorAll('input[type=checkbox]')].find(b => {{
            const t=(document.querySelector(`label[for="${{b.id}}"]`)?.innerText || '').trim().toLowerCase();
            return {json.dumps([v.lower() for v in prefs(value)])}.some(v => t === v || t.includes(v))}});
            return b && (document.querySelector(`label[for="${{b.id}}"]`) || b)}})()""")
        if not p:
            return f"checkbox option {value!r} not found"
        tab.click(p)
    elif f["type"] == "checkbox":
        if f["key"] == "acceptTermsAndAgreements" and ACCEPT_TERMS:
            pass  # the user said to tick Workday's own Terms box (--accept-terms); no other consent box is ever ticked
        elif re.search(r"terms|agree|consent|acknowledg|certif|attest", f["label"], re.I):
            return "consent checkbox: left for the user"
        if (value == "yes") != (f["value"] == "yes"):
            tab.click(tab.point(f"{field_js(k)}.querySelector('input[type=checkbox]')"))
    return None


def panel_js(name):
    return f'document.querySelector(\'[aria-labelledby="{name}"], [data-automation-id="{name}"]\')'


def keys(tab, text):
    for ch in text:
        cdp("Input.dispatchKeyEvent", session_id=tab.s, type="keyDown", key=ch, text=ch)
        cdp("Input.dispatchKeyEvent", session_id=tab.s, type="keyUp", key=ch)
    time.sleep(0.3)


def panel_value(tab, panel, key):
    return tab.js(f"""(()=>{{const f={panel}?.querySelector('[data-automation-id="formField-{key}"]'); if(!f) return null;
        const b=f.querySelector('button[aria-haspopup=listbox]'); if(b) return b.innerText.trim();
        const sel=[...f.querySelectorAll('[data-automation-id=selectedItem]')].map(e=>e.innerText.trim()); if(sel.length) return sel.join(', ');
        const c=f.querySelector('input[type=checkbox]'); if(c) return c.checked?'yes':'';
        const m=f.querySelector('[data-automation-id=dateSectionMonth-input]'), y=f.querySelector('[data-automation-id=dateSectionYear-input]');
        if(m||y) return [(m&&m.value)?String(m.value).padStart(2,'0'):'', y?y.value:''].filter(Boolean).join('/');
        const i=f.querySelector('textarea, input:not([type=hidden])'); return i? i.value.trim() : ''}})()""")


def set_date(tab, panel, key, mmyyyy):
    parts = mmyyyy.split("/")
    for part, sub in zip(parts[-2:] if len(parts) == 2 else parts, (["dateSectionMonth-input", "dateSectionYear-input"]
                                                                     if len(parts) == 2 else ["dateSectionYear-input"])):
        p = tab.point(f"{panel}?.querySelector('[data-automation-id=\"formField-{key}\"] [data-automation-id={sub}]')")
        if not tab.click(p):
            return f"date part {sub} not found"
        # a click on the box doesn't always focus its spinbutton (Adobe); focus it directly
        tab.js(f"{panel}?.querySelector('[data-automation-id=\"formField-{key}\"] [data-automation-id={sub}]').focus()")
        if tab.js("document.activeElement.value"):  # Backspace in an empty box jumps back to the month
            tab.js("document.activeElement.select && document.activeElement.select()")  # replace, don't append
            tab.key("Backspace", "Backspace", 8)
        if "Month" in sub:
            keys(tab, part)  # the month box takes key events and then jumps to the year
        else:
            tab.type(part)
    tab.key("Tab", "Tab", 9)
    return None


def fill_panel(tab, panel, want):
    """Write canonical values into one Work-Experience-N / Education-N panel; report what changed."""
    changes = []
    for key, value in want.items():
        if key in ("current", "start", "end"):
            continue
        have = panel_value(tab, panel, key)
        if have is None or (have or "").strip().lower() == str(value).strip().lower() or (isinstance(value, list) and matches(have, value)):
            continue
        f = tab.js(f"""(()=>{{const f={panel}.querySelector('[data-automation-id="formField-{key}"]');
            return f.querySelector('button[aria-haspopup=listbox]')?'select':(f.querySelector('[data-automation-id=multiselectInputContainer],[data-automation-id=selectedItemList]')?'prompt':
            (f.querySelector('[data-automation-id=dateSectionYear-input]')?'date':(f.querySelector('textarea')?'textarea':'text')))}})()""")
        if f == "date":
            for _ in range(3):
                err = set_date(tab, panel, key, str(value))
                if not err and str(value) in (panel_value(tab, panel, key) or ""):
                    break
                err = err or "did not stick"
        else:
            err = set_field(tab, {"key": key, "type": f, "value": have, "label": key}, value, scope=panel)
        now = panel_value(tab, panel, key) if not err else None
        if not err and now is not None and not (matches(now, value) if isinstance(value, list) else str(value).strip().lower() in now.strip().lower() or now.strip().lower() in str(value).strip().lower()):
            err = f"read back {now[:60]!r}"
        changes.append(f"{key}: {have!r} -> {value!r}" + (f" !! {err}" if err else ""))
    if "current" in want:
        have = panel_value(tab, panel, "currentlyWorkHere")
        if have is not None and (have == "yes") != bool(want["current"]):
            tab.click(tab.point(f"{panel}.querySelector('[data-automation-id=\"formField-currentlyWorkHere\"] input')"))
            changes.append(f"currentlyWorkHere -> {want['current']}")
    for key, k2 in (("start", "startDate"), ("end", "endDate")):
        if key in want and panel_value(tab, panel, k2) not in (None, want[key]):
            for _ in range(3):
                err = set_date(tab, panel, k2, want[key])
                if not err and panel_value(tab, panel, k2) == want[key]:
                    break
                err = err or f"read back {panel_value(tab, panel, k2)!r}"
            changes.append(f"{k2} -> {want[key]}" + (f" !! {err}" if err else ""))
    return changes


def fill_language(tab, panel):
    """Languages-N panel: the language itself is the parser's guess; every other dropdown is a proficiency level."""
    name = tab.js(f"""(()=>{{const f={panel}.querySelector('[data-automation-id^="formField-language"]') ||
        {panel}.querySelector('[data-automation-id^="formField-"]'); return (f.querySelector('button,[data-automation-id=selectedItem]')?.innerText||'').trim()}})()""")
    want = ANSWERS.get("languages", {}).get(name)
    if not want:
        return [f"{name!r}: no answer in wd_answers.json languages (leave for the user)"]
    changes = []
    box = tab.js(f"(()=>{{const c={panel}.querySelector('input[type=checkbox]'); return c? c.checked : null}})()")
    if box is not None and box != want["fluent"]:
        tab.click(tab.point(f"{panel}.querySelector('input[type=checkbox]')"))
        changes.append(f"{name} fluent -> {want['fluent']}")
    keys = tab.js(f"""[...{panel}.querySelectorAll('[data-automation-id^="formField-"]')].filter(f => f.querySelector('button[aria-haspopup=listbox]')
        && !/^language/i.test(f.getAttribute('data-automation-id').slice(10))).map(f => f.getAttribute('data-automation-id').slice(10))""") or []
    for key in keys:
        have = panel_value(tab, panel, key) or ""
        if matches(have, want["level"]):
            continue
        for _ in range(3):
            err = set_field(tab, {"key": key, "type": "select", "value": have, "label": key}, want["level"], scope=panel)
            if not err and matches(panel_value(tab, panel, key) or "", want["level"]):
                break
            err = err or "did not stick"
        else:
            changes.append(f"{name} {key[:8]}: !! {err}")
            continue
        err = None
        changes.append(f"{name} {key[:8]}: -> {want['level'][0]}" + (f" !! {err}" if err else ""))
    return changes


def work_panels(tab):
    return tab.js("[...document.querySelectorAll('[aria-labelledby$=\"-panel\"]')].map(e => e.getAttribute('aria-labelledby'))"
                  ".filter(n => /^Work-Experience-\\d+-panel$/.test(n))") or []


def fix_experience(tab):
    out, used = [], set()
    for job in ANSWERS.get("experience", []):
        # match by company, then take a blank panel the parser left, else press Add; never overwrite another job
        panel = None
        for name in work_panels(tab):
            if name in used:
                continue
            pj = panel_js(name)
            company = (panel_value(tab, pj, "companyName") or "").strip().lower()
            title = (panel_value(tab, pj, "jobTitle") or "").strip().lower()
            if company and (company in job["companyName"].lower() or job["companyName"].lower() in company):
                panel = name
                break
            if not company and title and title == job["jobTitle"].lower():  # parser kept the title, lost the company
                panel = name
                break
        if not panel:
            for name in work_panels(tab):
                pj = panel_js(name)
                if name not in used and not (panel_value(tab, pj, "companyName") or "").strip() \
                        and not (panel_value(tab, pj, "jobTitle") or "").strip():
                    panel = name
                    break
        if not panel:
            before = set(work_panels(tab))
            tab.click(tab.point("document.querySelector('[data-automation-id=\"Work-Experience-section\"] [data-automation-id=add-button], [aria-labelledby=\"Work-Experience-section\"] [data-automation-id=add-button], [data-automation-id=add-button]')"))
            time.sleep(2)
            new = [n for n in work_panels(tab) if n not in before]
            if not new:
                out.append(f"Work-Experience: could not add a panel for {job['jobTitle']} @ {job['companyName']} (add it by hand)")
                continue
            panel = new[0]
            out.append(f"added a Work Experience panel for {job['jobTitle']} @ {job['companyName']}")
        used.add(panel)
        out += [f"job {job['companyName'][:12]} {c}" for c in fill_panel(tab, panel_js(panel), job)]
    for name in reversed([n for n in work_panels(tab) if n not in used]):  # parser leftovers (split or invented jobs)
        what = panel_value(tab, panel_js(name), "jobTitle") or "(untitled)"
        tab.click(tab.point(f"[...{panel_js(name)}.querySelectorAll('button')].find(b => b.innerText.trim() === 'Delete')"))
        time.sleep(1.5)
        dismiss_dialogs(tab)
        out.append(f"deleted leftover Work Experience panel {what!r}"
                   + (" !! still there" if name in work_panels(tab) and len(work_panels(tab)) > len(used) else ""))
    for i in range(1, 10):
        panel = panel_js(f"Languages-{i}-panel")
        if not tab.js(f"!!{panel}"):
            break
        out += [f"language {i} {c}" for c in fill_language(tab, panel)]
    for i, edu in enumerate(ANSWERS.get("education", []), 1):
        panel = panel_js(f"Education-{i}-panel")
        if tab.js(f"!!{panel}"):
            out += [f"education {i} {c}" for c in fill_panel(tab, panel, edu)]
    return out


REVIEW_KEYS = [(r"^how did you hear", "source"),
               (r"^(have you (previously )?(worked|been employed)|have you been employed by)", "candidateIsPreviousWorker")]


def review_check(tab):
    """Check the Review page section by section: each job in its own block, education in its own block, and every
    question whose answer we know shows exactly that answer. Prints one line per check; returns the failures."""
    raw = tab.js("document.body.innerText") or ""
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    text = " | ".join(lines)
    checks = []

    def check(name, ok):
        checks.append((name, bool(ok)))

    for e in ("Alex", "Van Sample", ANSWERS["by_key"]["addressLine1"], "32000", "010", UPLOAD.name):
        check(f"My Information shows {e}", re.search(re.escape(e), text, re.I))
    check("last name is not only 'Sample'", not re.search(r"Last Name \| Sample \|", text))

    work = text[text.find("Work Experience"):text.find("| Education |")] if "Work Experience" in text else ""
    blocks = re.split(r"Work Experience \d+ \|", work)[1:]
    for job in ANSWERS.get("experience", []):
        blk = next((b for b in blocks if job["companyName"].lower() in b.lower()), "")
        check(f"job {job['companyName']}: present", blk)
        check(f"job {job['companyName']}: title {job['jobTitle']}", job["jobTitle"].lower() in blk.lower())
        check(f"job {job['companyName']}: from {job['start']}", re.search(r"From \| " + re.escape(job["start"]), blk))
        if job.get("end"):
            check(f"job {job['companyName']}: to {job['end']}", re.search(r"To \| " + re.escape(job["end"]), blk))
        else:
            check(f"job {job['companyName']}: currently works here", re.search(r"I currently work here \| Yes", blk))
    check(f"exactly {len(ANSWERS.get('experience', []))} jobs listed", len(blocks) == len(ANSWERS.get("experience", [])))

    m = re.search(r"\| Education \| Education 1 \|(.*?)\| (Certifications|Languages|Skills|Resume)", text)
    sec = m.group(1) if m else ""
    for edu in ANSWERS.get("education", []):
        check(f"education school {edu['schoolName']}", edu["schoolName"] in sec)
        check(f"education field of study is {prefs(edu['fieldOfStudy'])[0]} (or equivalent)",
              any(v.lower() in sec.lower() for v in prefs(edu["fieldOfStudy"])))
        check(f"education years {edu['firstYearAttended']}-{edu['lastYearAttended']}",
              re.search(r"From \| " + edu["firstYearAttended"] + r" \| To \(Actual or Expected\) \| " + edu["lastYearAttended"], sec))

    # every question line whose answer we know must show that answer on the next line
    for i, line in enumerate(lines[:-1]):
        if not re.search(r"\?|\*$|^Please select", line):
            continue
        # the standard questions are answered by field key (per company), so look them up the same way here
        key = next((k for pat, k in REVIEW_KEYS if re.search(pat, line, re.I)), "")
        want = answer_for({"key": key, "label": norm(line)})
        if want is None or want == "__USER__" or (isinstance(want, str) and want.lower() == "yes" and "Terms" in line):
            continue
        check(f"answer to {norm(line)[:70]!r} is {prefs(want)[0]!r}", matches(lines[i + 1], want))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"   [{'ok' if ok else 'FAIL'}] {n}")
    return failed


def wait_for(tab, expr, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = tab.js(expr)
        except Exception:  # page navigating
            v = None
        if v:
            return v
        time.sleep(0.5)
    return None


def visible(selector):
    return f"(()=>{{const e=document.querySelector('{selector}'); return !!(e && e.offsetParent)}})()"


def start(tab):
    """From a job (or its /apply) page: decline cookies, Autofill with Resume, sign in via Google, attach the resume."""
    if wait_for(tab, "/page you are looking for doesn.t exist|no longer (accepting|available)/i.test(document.body.innerText)", 3):
        return "posting no longer exists"
    if wait_for(tab, "/already applied/i.test(document.body.innerText)", 1):
        return "already applied to this job"
    decline = tab.point("[...document.querySelectorAll('button')].find(b => /^(decline|reject)/i.test(b.innerText.trim()) && b.offsetParent)")
    if decline:
        tab.click(decline)
    if not wait_for(tab, "/\\/apply/.test(location.pathname)", 1):
        apply = wait_for(tab, "!!document.querySelector('[data-automation-id=adventureButton]')", 15)
        if apply:
            tab.click(tab.point("document.querySelector('[data-automation-id=adventureButton]')"))
    auto = wait_for(tab, "!![...document.querySelectorAll('a,button')].find(b => /autofill with resume/i.test(b.innerText) && b.offsetParent)", 15)
    if auto:
        tab.click(tab.point("[...document.querySelectorAll('a,button')].find(b => /autofill with resume/i.test(b.innerText) && b.offsetParent)"))
    state = wait_for(tab, "document.querySelector('[data-automation-id=GoogleSignInButton]')?.offsetParent ? 'signin' : "
                          "(document.querySelector('input[type=file]') ? 'upload' : "
                          "(document.querySelector('[data-automation-id=signInContent]')?.offsetParent ? 'password' : ''))", 20)
    if state == "password":
        return "sign-in page (email + password only): the applicant creates or signs in to the account in this tab, then rerun with --tab --start"
    if state == "signin":
        # account creation and sign-in are the applicant's (one click on "Sign in with Google"); then rerun with --tab --start
        return "sign-in page: the applicant signs in (or creates the account) in this tab, then rerun with --tab --start"
    if state != "upload":
        return "resume upload page did not appear"
    root = cdp("DOM.getDocument", session_id=tab.s, depth=-1, pierce=True)["root"]["nodeId"]
    node = cdp("DOM.querySelector", session_id=tab.s, nodeId=root, selector="input[type=file]")["nodeId"]
    UPLOAD.parent.mkdir(parents=True, exist_ok=True)
    UPLOAD.write_bytes(RESUME.read_bytes())
    cdp("DOM.setFileInputFiles", session_id=tab.s, nodeId=node, files=[str(UPLOAD)])
    if not wait_for(tab, visible("[data-automation-id=file-upload-successful]"), 30):
        return "resume upload did not finish"
    tab.click(tab.point("document.querySelector('[data-automation-id=pageFooterNextButton]')"))
    if not wait_for(tab, "/my information/i.test(document.querySelector('[data-automation-id=progressBarActiveStep]')?.innerText || '')", 40):
        return "did not reach My Information after the resume"
    return None


def open_tab(url):
    target = cdp("Target.createTarget", url=url)["targetId"]
    tab = Tab(target)
    wait_for(tab, "document.readyState === 'complete' && !!document.querySelector('[data-automation-id]')", 30)
    return tab


def settle(tab, quiet=2.0, timeout=20.0):
    """Wait until the page's fields stop changing; Workday re-renders a page after autofill and loses early clicks."""
    end, last, since = time.time() + timeout, None, time.time()
    while time.time() < end:
        sig = json.dumps(tab.js(FIELDS_JS)["fields"])
        if sig != last:
            last, since = sig, time.time()
        elif time.time() - since >= quiet:
            return
        time.sleep(0.4)


def next_page(tab, before):
    tab.click(tab.point("document.querySelector('[data-automation-id=pageFooterNextButton]')"))
    for _ in range(40):  # Workday saves take 5-15 s
        time.sleep(1)
        st = tab.js(FIELDS_JS)
        if st["step"] != before or st["errors"]:
            return st
    return tab.js(FIELDS_JS)


def main():
    require_primary()
    ap = argparse.ArgumentParser()
    ap.add_argument("--tab", help="existing tab: targetId prefix or URL substring")
    ap.add_argument("--url", help="job posting URL: opens a new tab and starts from scratch (implies --start)")
    ap.add_argument("--start", action="store_true")
    ap.add_argument("--accept-terms", action="store_true", help="tick Workday's own Terms and Conditions box (only when the user said to)")
    ap.add_argument("--max-pages", type=int, default=8)
    a = ap.parse_args()
    ensure_daemon()
    if bool(a.tab) == bool(a.url):
        ap.error("give exactly one of --tab or --url")
    tab = open_tab(a.url) if a.url else Tab(a.tab)
    print(f"tab {tab.target[:8]}")
    global TENANT, ACCEPT_TERMS
    ACCEPT_TERMS = a.accept_terms
    TENANT = (tab.js("location.hostname") or "").split(".")[0]
    if a.start or a.url:
        err = start(tab)
        if err:
            print("START FAILED: " + err)
            return 5
    for _ in range(a.max_pages):
        settle(tab)
        st = tab.js(FIELDS_JS)
        print(f"== {st['step']}")
        if re.search(r"sign in|create account", st["step"], re.I):
            print("SIGN-IN needed: the user signs in to this company's Workday account (never Claude).")
            return 5
        if st["errors"] and re.search(r"review", st["step"], re.I):
            print("ERRORS on page:")
            for e in st["errors"]:
                print("   - " + e[:200])
            return 4
        if re.search(r"review", st["step"], re.I):
            print("REVIEW reached: checking every value before the user submits.")
            missing = review_check(tab)
            print("REVIEW CHECK: " + ("PASS" if not missing else "FAIL: " + "; ".join(missing)))
            return 0 if not missing else 4
        changes = []
        if re.search(r"my experience", st["step"], re.I):
            changes = fix_experience(tab)
            for c in changes:
                print("   " + c.replace("\n", " ")[:200])
        dismiss_dialogs(tab)
        decide, yours, stuck, expected = [], [], [], {}
        if re.search(r"my experience", st["step"], re.I):
            stuck += [c for c in changes if "!!" in c or "could not add" in c]
        st = tab.js(FIELDS_JS)
        for f in st["fields"]:
            if f["type"] == "file" or (re.search(r"my experience", st["step"], re.I) and (f["panel"] or f["key"] in PANEL_KEYS)):
                if f["required"] and not f["value"]:
                    stuck.append(f"{norm(f['label'])}: still empty in a {f['panel'] or 'file'} section")
                continue
            want = answer_for(f)
            if want == "__USER__" or (want is None and any(re.search(p, f["label"], re.I) for p in ANSWERS.get("user_only", []))):
                if f["required"] and not f["value"]:
                    yours.append(f)
                continue
            if want is None:
                if f["required"] and not f["value"]:
                    decide.append(f)
                continue
            if f["value"] and (matches(f["value"], want) or not (f["key"] in ANSWERS["enforce"]
                                                       or re.search(ANSWERS.get("enforce_labels", "$^"), f["label"], re.I))):
                continue  # keep autofilled values unless the key is on the enforce list
            err = None
            for _ in range(3):
                dismiss_dialogs(tab)
                err = set_field(tab, f, want)
                time.sleep(1.0)
                now = next((x["value"] for x in tab.js(FIELDS_JS)["fields"] if x["key"] == f["key"]), "")
                if not err and matches(now, want):
                    break
                err = err or f"read back {now!r}"
                f = dict(f, value=now)
            expected[f["key"]] = want
            print(f"   set {f['key']} = {want!r}" + (f"  !! {err}" if err else ""))
            if err:
                stuck.append(f"{norm(f['label'])}: {err}")
        # gate: never save a page unless every answer we gave still reads back (fixing later needs Back, which Workday mishandles)
        now = {x["key"]: x["value"] for x in tab.js(FIELDS_JS)["fields"]}
        stuck += [f"{k}: reads {now.get(k)!r} before saving, wanted {v!r}" for k, v in expected.items()
                  if not matches(now.get(k) or "", v)]
        if decide or yours or stuck:
            for f in yours:
                print("   - YOURS: " + norm(f["label"]))
            for f in decide:
                print("   - DECIDE: " + norm(f["label"]))
            for x in stuck:
                print("   - STUCK: " + x)
            print(f"PENDING written to {write_pending(tab, st['step'], decide, yours, stuck)}")
            return 3 if not stuck else 4
        st2 = next_page(tab, st["step"])
        if st2["errors"]:
            print("ERRORS after Save and Continue:")
            for e in st2["errors"]:
                print("   - " + e[:200])
            return 4
    return 4


if __name__ == "__main__":
    sys.exit(main())
