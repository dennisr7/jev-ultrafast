"""Create or sign in to a Workday tenant account with a Keychain-held password (2026-10-24).

uv run python scripts/wd_credentials.py --tab <targetId prefix | url substring> [--accept-terms]
uv run python scripts/wd_credentials.py --has <tenant>        prints STORED or NONE

the applicant chose (2026-10-24) to have accounts created for him. Passwords never leave this process: each one is random
(secrets), unique per tenant, written to the macOS Keychain (service "workday:<tenant>") through `security -i` on
stdin (never argv) before the form is submitted, and typed into the page with CDP Input.insertText. Output is status
words only, never values: ACCOUNT_CREATED, CREDENTIALS_STORED, AUTHENTICATION_SUCCESSFUL,
VERIFICATION_EMAIL_SENT, AUTHENTICATION_REQUIRES_USER: <reason>.
--accept-terms ticks the create-account agreement box; without it the run stops there (a legal agreement is the applicant's).
CAPTCHA, MFA and email links are never worked around: they come back as AUTHENTICATION_REQUIRES_USER.
Exit codes: 0 signed in, 3 needs the applicant or email verification, 4 failed.
"""

import argparse
import re
import secrets
import string
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_harness.admin import ensure_daemon  # noqa: E402
from browser_harness.helpers import cdp  # noqa: E402
from wd_apply import Tab, wait_for  # noqa: E402
from profile_guard import require_primary  # noqa: E402

EMAIL = "alex.sample@example.com"
SPECIAL = "!@#$%^&*-_=+?"


def service(tenant):
    return f"workday:{tenant}"


def generate():
    """24 chars with every class Workday tenants ask for; no quotes or backslashes (safe inside `security -i`)."""
    alphabet = string.ascii_letters + string.digits + SPECIAL
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(24))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in SPECIAL for c in pw)):
            return pw


def store(tenant, url, pw):
    cmd = (f'add-generic-password -U -s "{service(tenant)}" -a "{EMAIL}" -l "Workday {tenant}" '
           f'-j "{url.split("?")[0][:200]}" -w "{pw}"\n')
    r = subprocess.run(["security", "-i"], input=cmd, capture_output=True, text=True)
    if r.returncode != 0 or "error" in (r.stdout + r.stderr).lower():
        raise RuntimeError("Keychain write failed")  # no subprocess text: it could echo the command


def load(tenant):
    r = subprocess.run(["security", "find-generic-password", "-s", service(tenant), "-a", EMAIL, "-w"],
                       capture_output=True, text=True)
    return r.stdout.rstrip("\n") if r.returncode == 0 else None


def type_into(tab, selector, text):
    root = cdp("DOM.getDocument", session_id=tab.s, depth=-1, pierce=True)["root"]["nodeId"]
    node = cdp("DOM.querySelector", session_id=tab.s, nodeId=root, selector=selector)["nodeId"]
    if not node:
        raise RuntimeError(f"field {selector} not found")
    cdp("DOM.focus", session_id=tab.s, nodeId=node)
    tab.js(f"(()=>{{const e=document.querySelector('{selector}'); e.select && e.select(); return true}})()")
    cdp("Input.insertText", session_id=tab.s, text=text)
    time.sleep(0.4)


def press(tab, automation_id):
    """Mouse click first; some tabs (Samsung) ignore CDP mouse events on links, so then a DOM click."""
    sel = f"document.querySelector('[data-automation-id={automation_id}]')"
    before = tab.js(STATE_JS)
    if not tab.click(tab.point(sel)):
        return False
    time.sleep(1.5)
    if tab.js(STATE_JS) == before:
        tab.js(f"{sel}?.click()")
    return True


def submit(tab, automation_id):
    """Workday covers its submit buttons with a click_filter div: click it, then DOM-click the button if nothing moved."""
    before = tab.js(STATE_JS)
    p = tab.point(f"(()=>{{const b=document.querySelector('[data-automation-id={automation_id}]'); "
                  f"return b && (b.parentElement.querySelector('[data-automation-id=click_filter]') || b)}})()")
    if not p:
        raise RuntimeError(f"no {automation_id}")
    tab.click(p)
    time.sleep(3)
    if tab.js(STATE_JS) == before:
        tab.js(f"document.querySelector('[data-automation-id={automation_id}]')?.click()")


STATE_JS = r"""(() => {
  const v = s => { const e = document.querySelector(s); return !!(e && e.offsetParent); };
  const text = document.body.innerText;
  if (/captcha/i.test(document.body.innerHTML) && v('iframe[src*=captcha],iframe[title*=captcha i]')) return 'captcha';
  if (/verify your (account|email)|verification email|check your email/i.test(text)) return 'verify';
  if (v('[data-automation-id=verifyPassword]')) return 'create';
  if (v('[data-automation-id=password]')) return 'signin';
  if (v('[data-automation-id=SignInWithEmailButton]')) return 'choose';
  if (v('[data-automation-id=GoogleSignInButton]') || v('[data-automation-id=signInLink]')) return 'gate';
  return 'in';
})()"""


def errors(tab):
    return tab.js("[...document.querySelectorAll('[data-automation-id=errorMessage],[role=alert]')]"
                  ".filter(e=>e.offsetParent).map(e=>e.innerText.trim()).filter(Boolean).join(' | ')") or ""


def done(code, msg):
    print(msg)
    return code


def run(tab, tenant, accept_terms):
    for _ in range(6):
        state = wait_for(tab, STATE_JS, 10) or "in"
        if state == "captcha":
            return done(3, "AUTHENTICATION_REQUIRES_USER: CAPTCHA")
        if state == "verify":
            return done(3, "VERIFICATION_EMAIL_SENT")
        if state == "in":
            return done(0, "AUTHENTICATION_SUCCESSFUL")
        if state == "choose":
            press(tab, "SignInWithEmailButton")
        elif state == "gate":
            link = "createAccountLink" if load(tenant) is None else "signInLink"
            if not press(tab, link):
                return done(3, "AUTHENTICATION_REQUIRES_USER: only Google sign-in offered")
        elif state == "signin":
            pw = load(tenant)
            if pw is None:
                if not press(tab, "createAccountLink"):
                    return done(3, "AUTHENTICATION_REQUIRES_USER: no stored password and no Create Account link")
                continue
            type_into(tab, "[data-automation-id=email]", EMAIL)
            type_into(tab, "[data-automation-id=password]", pw)
            del pw
            submit(tab, "signInSubmitButton")
            time.sleep(2)
            if (wait_for(tab, STATE_JS, 5) or "in") == "signin":
                return done(4, "AUTHENTICATION_FAILED: " + (errors(tab)[:200] or "still on sign-in"))
        elif state == "create":
            if load(tenant) is not None:  # account exists: switch to the sign-in form
                if not press(tab, "signInLink"):
                    return done(3, "AUTHENTICATION_REQUIRES_USER: password stored but no Sign In link on the create form")
                continue
            box = tab.js("(()=>{const e=document.querySelector('[data-automation-id=createAccountCheckbox]'); return !!(e && e.offsetParent)})()")
            if box and not accept_terms:
                return done(3, "AUTHENTICATION_REQUIRES_USER: create-account agreement checkbox (rerun with --accept-terms if the applicant agrees)")
            pw = generate()
            store(tenant, tab.js("location.href"), pw)
            print("CREDENTIALS_STORED")
            type_into(tab, "[data-automation-id=email]", EMAIL)
            type_into(tab, "[data-automation-id=password]", pw)
            type_into(tab, "[data-automation-id=verifyPassword]", pw)
            del pw
            if box:
                tab.click(tab.point("document.querySelector('[data-automation-id=createAccountCheckbox]')"))
            submit(tab, "createAccountSubmitButton")
            time.sleep(5)
            after = wait_for(tab, STATE_JS, 5) or "in"
            if after == "create":
                return done(4, "ACCOUNT_CREATION_FAILED: " + (errors(tab)[:200] or "still on the form"))
            if after == "signin":  # Workday bounces an existing email to Sign In; the new password is useless
                subprocess.run(["security", "delete-generic-password", "-s", service(tenant), "-a", EMAIL], capture_output=True)
                return done(3, "AUTHENTICATION_REQUIRES_USER: an account already exists for this email (reset the password or sign in)")
            print("ACCOUNT_CREATED")
        time.sleep(2)
    return done(4, "AUTHENTICATION_FAILED: sign-in flow did not settle")


def main():
    require_primary()
    ap = argparse.ArgumentParser()
    ap.add_argument("--tab")
    ap.add_argument("--has")
    ap.add_argument("--accept-terms", action="store_true")
    a = ap.parse_args()
    if a.has:
        print("STORED" if load(a.has) is not None else "NONE")
        return 0
    if not a.tab:
        ap.error("give --tab or --has")
    ensure_daemon()
    tab = Tab(a.tab)
    tenant = (tab.js("location.hostname") or "").split(".")[0]
    try:
        return run(tab, tenant, a.accept_terms)
    except Exception as e:  # message only, no traceback (locals could hold the password)
        return done(4, f"AUTHENTICATION_FAILED: {type(e).__name__}: {re.sub(r'[^ -~]', '', str(e))[:150]}")


if __name__ == "__main__":
    sys.exit(main())
