#!/bin/sh
# Show or switch the active candidate profile (profiles/active -> profiles/<name>).
# The choice persists across sessions until switched again.
#   tools/profile.sh            print the active profile
#   tools/profile.sh list       list profiles
#   tools/profile.sh <name>     switch to profiles/<name>
set -e
cd "$(dirname "$0")/../profiles"
current() { [ -L active ] && basename "$(readlink active)" || echo none; }
case "${1:-}" in
  "") current ;;
  list) for d in */; do d=${d%/}; [ "$d" = active ] && continue; [ "$d" = "$(current)" ] && echo "* $d" || echo "  $d"; done ;;
  *)
    name=$1
    [ -f "$name/profile.md" ] || { echo "no profile '$name' (have: $(ls -d */ | tr -d / | tr '\n' ' '))" >&2; exit 1; }
    ln -sfn "$name" active
    echo "active profile: $name ($(sed -n '1s/^# Candidate Profile: //p' "$name/profile.md"))"
    ;;
esac
