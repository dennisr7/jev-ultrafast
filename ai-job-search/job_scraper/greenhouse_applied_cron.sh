#!/bin/bash
# Run by launchd every 15 minutes (see your own LaunchAgents plist for this job).
# Skips quietly when Chrome isn't open, so it never launches Chrome on its own.
pgrep -xq "Google Chrome" || { echo "$(date '+%F %T') Chrome not running; skipped"; exit 0; }
echo "$(date '+%F %T') run"
cd "$(dirname "$0")/../jev-ultrafast" || exit 1
exec "${UV:-uv}" run python ../job_scraper/greenhouse_applied.py 2>&1 | tail -4
