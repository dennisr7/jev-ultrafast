"""The answers, resume and Keychain accounts these scripts use belong to the `primary` profile.

A workspace can hold several candidates; profiles/active says who is being applied for. Refuse to run for anyone
else rather than submit one person's data under another person's name.
"""

import sys
from pathlib import Path

ACTIVE = Path(__file__).resolve().parents[2] / "profiles" / "active"


def require_primary():
    if ACTIVE.is_symlink() and ACTIVE.resolve().name != "primary":
        sys.exit(f"Active profile is '{ACTIVE.resolve().name}', but this script only holds the primary candidate's "
                 "answers and accounts. Switch with tools/profile.sh primary, or apply for the other profile by hand.")
