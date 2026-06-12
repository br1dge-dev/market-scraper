#!/usr/bin/env python3
"""
generate.py — Generator für alle launchd Plists des Cardmarket Trackers.

Single source of truth für Job-Definitionen. Schreibt eine Plist pro Job
ins gleiche Verzeichnis. Plists werden im Git getrackt.

Usage:
    cd launchd && python3 generate.py
"""

import os
from pathlib import Path

WORKDIR = "/Users/robert/Projects/cardmarket-tracker"
PYTHON = "/usr/bin/python3"
LABEL_PREFIX = "com.br1dge.cardmarket."

# Job definitions: (slug, script, args, schedule)
# schedule = list of dicts, each like {'Minute': N, 'Hour': N, 'Weekday': N}
#   Weekday: 0=Sun, 1=Mon ... 6=Sat (launchd convention)
JOBS = [
    # === SCRAPER (stündlich, versetzt) ===
    {
        'slug': 'unleashed',
        'script': 'scraper.py', 'args': ['unleashed'],
        'schedule': [{'Minute': 2}],
    },
    {
        'slug': 'dazzling-aurora',
        'script': 'scraper.py', 'args': ['dazzling-aurora'],
        'schedule': [{'Minute': 12}],
    },
    {
        'slug': 'worlds-bundle',
        'script': 'scraper.py', 'args': ['worlds-bundle'],
        'schedule': [{'Minute': 17}],
    },
    {
        'slug': 'origins',
        'script': 'scraper.py', 'args': ['origins'],
        'schedule': [{'Minute': 27}],
    },
    {
        'slug': 'spiritforged',
        'script': 'scraper.py', 'args': ['spiritforged'],
        'schedule': [{'Minute': 42}],
    },
    {
        'slug': 'arcane',
        'script': 'scraper.py', 'args': ['arcane'],
        'schedule': [{'Minute': 57}],
    },

    # === REPORTS ===
    {
        'slug': 'daily-report',
        'script': 'daily_report_v2.py', 'args': [],
        'schedule': [{'Hour': 8, 'Minute': 0}, {'Hour': 18, 'Minute': 0}],
    },
    {
        'slug': 'weekly-report',
        'script': 'weekly_report_v2.py', 'args': [],
        'schedule': [{'Weekday': 0, 'Hour': 21, 'Minute': 0}],  # Sunday
    },

    # === PRICE ALERTS ===
    {
        'slug': 'price-alerts',
        'script': 'price_alerts.py', 'args': [],
        'schedule': [{'Hour': 8, 'Minute': 30}, {'Hour': 18, 'Minute': 30}],
    },

    # === WATCHDOG (alle 3h) ===
    {
        'slug': 'watchdog',
        'script': 'watchdog.py', 'args': [],
        'schedule': [{'Hour': h, 'Minute': 0} for h in range(0, 24, 3)],
    },

    # === BACKUP (3:00) ===
    {
        'slug': 'backup',
        'script': 'backup_db.py', 'args': [],
        'schedule': [{'Hour': 3, 'Minute': 0}],
    },

    # === DotGG Collection (alle 6h, versetzt) ===
    {
        'slug': 'collection-sync',
        'script': 'collection_sync.py', 'args': [],
        'schedule': [{'Hour': h, 'Minute': 15} for h in (4, 10, 16, 22)],
    },
    {
        'slug': 'collection-alerts',
        'script': 'collection_alerts.py', 'args': [],
        'schedule': [{'Hour': h, 'Minute': 20} for h in (4, 10, 16, 22)],
    },
]


PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>

    <key>ProgramArguments</key>
    <array>
{program_args}
    </array>

    <key>WorkingDirectory</key>
    <string>{workdir}</string>

    <key>StartCalendarInterval</key>
{schedule_xml}

    <key>StandardOutPath</key>
    <string>/tmp/cardmarket-{slug}.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/cardmarket-{slug}.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>/Users/robert</string>
    </dict>

    <key>RunAtLoad</key>
    <false/>

    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
"""


def schedule_to_xml(schedule):
    """Convert schedule list to <dict> or <array><dict>...</dict></array>."""
    def one(entry):
        lines = ["        <dict>"]
        for key in ('Minute', 'Hour', 'Day', 'Month', 'Weekday'):
            if key in entry:
                lines.append(f"            <key>{key}</key>")
                lines.append(f"            <integer>{entry[key]}</integer>")
        lines.append("        </dict>")
        return "\n".join(lines)

    if len(schedule) == 1:
        return f"    <dict>\n" + "\n".join(
            f"        <key>{k}</key>\n        <integer>{v}</integer>"
            for k, v in schedule[0].items()
        ) + "\n    </dict>"

    inner = "\n".join(one(e) for e in schedule)
    return f"    <array>\n{inner}\n    </array>"


def generate():
    out_dir = Path(__file__).parent
    written = []

    for job in JOBS:
        slug = job['slug']
        label = f"{LABEL_PREFIX}{slug}"
        args = [PYTHON, job['script']] + job['args']
        program_args = "\n".join(f"        <string>{a}</string>" for a in args)
        schedule_xml = schedule_to_xml(job['schedule'])

        content = PLIST_TEMPLATE.format(
            label=label,
            program_args=program_args,
            workdir=WORKDIR,
            schedule_xml=schedule_xml,
            slug=slug,
        )

        out_path = out_dir / f"{label}.plist"
        out_path.write_text(content)
        written.append(out_path.name)

    print(f"✅ {len(written)} Plists generiert:")
    for name in written:
        print(f"   • {name}")


if __name__ == "__main__":
    generate()
