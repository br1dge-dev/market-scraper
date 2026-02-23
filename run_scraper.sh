#!/bin/bash
# Wrapper for cardmarket scraper to ensure proper environment

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/Users/robert/.local/bin:$PATH"
export HOME="/Users/robert"
export USER="robert"

# Add user site-packages to Python path
export PYTHONPATH="/Users/robert/Library/Python/3.9/lib/python/site-packages:$PYTHONPATH"

# Log file for debugging
LOGFILE="/Users/robert/.openclaw/workspace/skills/cardmarket-tracker/cron.log"

# Run the scraper with logging
cd /Users/robert/.openclaw/workspace/skills/cardmarket-tracker
echo "=== $(date): Starting scraper for $1 ===" >> "$LOGFILE"
/usr/bin/python3 scraper.py "$@" >> "$LOGFILE" 2>&1
EXIT_CODE=$?
echo "=== $(date): Exited with code $EXIT_CODE ===" >> "$LOGFILE"
exit $EXIT_CODE
