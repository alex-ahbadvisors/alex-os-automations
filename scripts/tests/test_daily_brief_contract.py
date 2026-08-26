#!/usr/bin/env python3
"""
test_daily_brief_contract.py -- hermetic contract tests for the [8] Daily
Brief workflow (relay-migration/8-daily-brief-MODIFIED.json), build 348B.

WHY A NODE SUBPROCESS, NOT A PYTHON REIMPLEMENTATION
  The bug this build fixes lives inside the 'Deterministic Assembly' n8n Code
  node's actual JavaScript. A Python re-implementation of the same math would
  test a parallel guess at the logic, not the shipped source -- exactly the
  gap that let the original bug ship unnoticed. Instead, this test EXTRACTS
  the real `jsCode` string from the JSON and runs it, unmodified, under the
  system `node` binary (already a sanctioned dependency here -- see
  n8n-failure-patterns.md P018, `node --check` on every Code node body).

HERMETIC: a small Luxon-compatible `DateTime` shim (ET-aware, DST-correct via
Node's built-in Intl/ICU) and a `$` mock stand in for the n8n sandbox globals.
No npm install, no network, no live n8n. Node is invoked as a local
subprocess only -- this makes zero network calls.

Covers:
  A  the trigger node fires Mon-Fri only (structural cron check) at the
     proven-compatible typeVersion (round 2).
  B  August 25 exact fixture: occupied_minutes=375, free_minutes=225, total
     600; a triple overlap counts once; the one-denominator glance line.
  C  before-window-only and after-window-only meetings (excluded from the
     primary occupied/free pair, still surfaced on their own line).
  D  a multi-day event, clamped to today only.
  E  DST: both the spring-forward and fall-back transition days still
     resolve an exact 600-minute (8am-6pm) window.
  F  largest free gap, in integer minutes.
  G  a clear calendar (zero events).
  H  persisted metrics (meetingHours/freeHours/occupiedMinutes/freeMinutes)
     share one denominator and sum exactly (round 2).
  I  the standalone n8n/code-nodes/deterministic-assembly-v3.1.js copy is
     byte-identical to the workflow node's jsCode (round 2 -- the standalone
     file had drifted stale and would reintroduce the old bug if restored).
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - repo's stated floor is Python 3.9+
    print("SKIP: zoneinfo unavailable (need Python 3.9+)", file=sys.stderr)
    sys.exit(0)

HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOW_PATH = os.path.join(HERE, "..", "..", "relay-migration", "8-daily-brief-MODIFIED.json")
STANDALONE_PATH = os.path.join(HERE, "..", "..", "n8n", "code-nodes", "deterministic-assembly-v3.1.js")
ET = ZoneInfo("America/New_York")
FAILS = []


def check(cond, name):
    if cond:
        print("  PASS  " + name)
    else:
        print("  FAIL  " + name)
        FAILS.append(name)


def _et(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=ET)


def et_ms(y, mo, d, h, mi, s=0):
    return int(_et(y, mo, d, h, mi, s).timestamp() * 1000)


def et_iso(y, mo, d, h, mi, s=0):
    return _et(y, mo, d, h, mi, s).isoformat()


# -----------------------------------------------------------------------------
# Load the workflow, extract the two nodes this build touches
# -----------------------------------------------------------------------------
with open(WORKFLOW_PATH, encoding="utf-8") as fh:
    WORKFLOW = json.load(fh)

NODES = {n["name"]: n for n in WORKFLOW["nodes"]}
TRIGGER = NODES.get("7:45 AM Weekday Trigger")
ASSEMBLY = NODES.get("Deterministic Assembly")

if not (subprocess.run(["node", "--version"], capture_output=True).returncode == 0):
    print("SKIP: node binary not found on PATH", file=sys.stderr)
    sys.exit(0)

# ---------------------------------------------------------------------------
print("A. trigger node is genuinely weekday-only, at a proven typeVersion")
# ---------------------------------------------------------------------------
check(TRIGGER is not None, "trigger node exists")
rule = (TRIGGER or {}).get("parameters", {}).get("rule", {}).get("interval", [{}])[0]
check(rule.get("field") == "cronExpression", "trigger uses a cron expression, not bare hour/minute")
expr = rule.get("expression", "")
fields = expr.split()
check(len(fields) == 5, "cron expression has 5 fields: %r" % expr)
if len(fields) == 5:
    minute, hour, dom, month, dow = fields
    check(minute == "45" and hour == "7", "still fires at 7:45")

    def fires_on(weekday_field, day_num):
        """day_num: cron convention, 0 and 7 both mean Sunday."""
        for part in weekday_field.split(","):
            if "-" in part:
                lo, hi = (int(x) for x in part.split("-"))
                if lo <= day_num <= hi:
                    return True
            elif part == "*":
                return True
            elif int(part) % 7 == day_num % 7:
                return True
        return False

    fires = {d: fires_on(dow, d) for d in range(8)}
    check(all(fires[d] for d in (1, 2, 3, 4, 5)), "fires Monday-Friday: %r" % expr)
    check(not fires[0] and not fires[6] and not fires[7],
          "does NOT fire Saturday/Sunday (weekday=0/6/7): %r" % expr)

# Round-2 finding: cronExpression needs a typeVersion this repo has already
# proven working. n8n-workflows/weekly-goals-reminder.json's "Monday 9 AM
# Trigger" runs cronExpression at 1.3 -- that is the precedented choice this
# node now matches, rather than staying on the old bare-hour/minute node's 1.2.
check(TRIGGER.get("typeVersion") == 1.3,
      "trigger uses typeVersion 1.3, matching this repo's other working "
      "cronExpression trigger, not left on the old node's 1.2: %r" % TRIGGER.get("typeVersion"))

check(ASSEMBLY is not None, "Deterministic Assembly node exists")
JS_CODE = ASSEMBLY["parameters"]["jsCode"]
check("' calendar '" in JS_CODE and "'entries'" in JS_CODE,
      "headline builds 'N calendar entries/entry', not an additive meeting count (proven at runtime in B/C/G below)")
check("occupiedMin" in JS_CODE and "freeMin" in JS_CODE,
      "integer-minute variables present in the node source")

# ---------------------------------------------------------------------------
print("I. the standalone code-node copy is byte-identical to the workflow node")
# ---------------------------------------------------------------------------
try:
    with open(STANDALONE_PATH, encoding="utf-8") as fh:
        standalone_js = fh.read()
    check(standalone_js == JS_CODE,
          "n8n/code-nodes/deterministic-assembly-v3.1.js == the workflow node's jsCode "
          "(this file had drifted stale before round 2 and would reintroduce the old "
          "bug if anyone ever restored a workflow from it)")
except OSError as exc:
    check(False, "standalone code-node file readable: %s" % exc)

# ---------------------------------------------------------------------------
# Hermetic JS harness: a minimal Luxon-compatible DateTime (ET-aware, DST-
# correct via Intl) and a $ mock. Injected ahead of the real extracted code,
# which is executed unmodified inside `new Function(...)` so a top-level
# `return` (valid in an n8n Code node body) works the same way here.
# ---------------------------------------------------------------------------
HARNESS_JS = r"""
'use strict';
const ZONE = 'America/New_York';
const WEEKDAY_NAMES = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
const MONTH_NAMES = ['January','February','March','April','May','June','July','August','September','October','November','December'];

function partsInZone(utcMs, zone) {
  const dtf = new Intl.DateTimeFormat('en-US', {
    timeZone: zone, hourCycle: 'h23',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
  const parts = {};
  for (const p of dtf.formatToParts(new Date(utcMs))) parts[p.type] = p.value;
  return {
    year: +parts.year, month: +parts.month, day: +parts.day,
    hour: (+parts.hour) % 24, minute: +parts.minute, second: +parts.second
  };
}

function zonedToUtc(spec, zone) {
  let guess = Date.UTC(spec.year, spec.month - 1, spec.day, spec.hour, spec.minute, spec.second || 0, spec.millisecond || 0);
  for (let i = 0; i < 3; i++) {
    const got = partsInZone(guess, zone);
    const gotMs = Date.UTC(got.year, got.month - 1, got.day, got.hour, got.minute, got.second);
    const wantMs = Date.UTC(spec.year, spec.month - 1, spec.day, spec.hour, spec.minute, spec.second || 0);
    const diff = wantMs - gotMs;
    if (diff === 0) break;
    guess += diff;
  }
  return guess;
}

function isoWeekInfo(y, m, d) {
  const date = new Date(Date.UTC(y, m - 1, d));
  const dayNum = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - dayNum + 3);
  const firstThursday = new Date(Date.UTC(date.getUTCFullYear(), 0, 4));
  const firstDayNum = (firstThursday.getUTCDay() + 6) % 7;
  firstThursday.setUTCDate(firstThursday.getUTCDate() - firstDayNum + 3);
  const week = 1 + Math.round((date - firstThursday) / (7 * 86400000));
  return { week, weekYear: date.getUTCFullYear() };
}

function makeDT(utcMs, zone) {
  const p = partsInZone(utcMs, zone);
  const jsDow = new Date(Date.UTC(p.year, p.month - 1, p.day)).getUTCDay();
  const iso = isoWeekInfo(p.year, p.month, p.day);
  return {
    _ms: utcMs, _zone: zone,
    day: p.day,
    weekNumber: iso.week,
    setZone(z) { return makeDT(this._ms, z); },
    toMillis() { return this._ms; },
    set(spec) {
      const merged = Object.assign({ year: p.year, month: p.month, day: p.day,
        hour: p.hour, minute: p.minute, second: p.second, millisecond: 0 }, spec);
      return makeDT(zonedToUtc(merged, this._zone), this._zone);
    },
    startOf(unit) {
      if (unit !== 'day') throw new Error('startOf: unsupported unit ' + unit);
      return makeDT(zonedToUtc({ year: p.year, month: p.month, day: p.day, hour: 0, minute: 0, second: 0, millisecond: 0 }, this._zone), this._zone);
    },
    endOf(unit) {
      if (unit !== 'day') throw new Error('endOf: unsupported unit ' + unit);
      return makeDT(zonedToUtc({ year: p.year, month: p.month, day: p.day, hour: 23, minute: 59, second: 59, millisecond: 999 }, this._zone), this._zone);
    },
    toFormat(fmt) {
      const pad2 = n => String(n).padStart(2, '0');
      switch (fmt) {
        case 'yyyy-MM-dd': return p.year + '-' + pad2(p.month) + '-' + pad2(p.day);
        case 'MMMM d, yyyy': return MONTH_NAMES[p.month - 1] + ' ' + p.day + ', ' + p.year;
        case 'EEEE': return WEEKDAY_NAMES[jsDow];
        case 'kkkk': return String(iso.weekYear);
        case 'yyyy-MM-dd HH:mm': return p.year + '-' + pad2(p.month) + '-' + pad2(p.day) + ' ' + pad2(p.hour) + ':' + pad2(p.minute);
        case 'h:mm a': {
          let h = p.hour % 12; if (h === 0) h = 12;
          return h + ':' + pad2(p.minute) + ' ' + (p.hour < 12 ? 'AM' : 'PM');
        }
        default: throw new Error('toFormat: unsupported token ' + fmt);
      }
    }
  };
}

global.__FIXED_NOW_MS = null;
global.DateTime = {
  now() { return makeDT(global.__FIXED_NOW_MS !== null ? global.__FIXED_NOW_MS : Date.now(), ZONE); },
  fromMillis(ms) { return makeDT(ms, ZONE); }
};

global.__CALENDAR_EVENTS = [];
global.$ = function (name) {
  if (name === 'Format Calendar') {
    return { all: () => global.__CALENDAR_EVENTS.map(e => ({ json: e })) };
  }
  return { first: () => ({ json: {} }), all: () => [] };
};
"""

RUNNER_JS = r"""
'use strict';
const fs = require('fs');
const [, , harnessPath, fixturePath, codePath] = process.argv;
require(harnessPath);
const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
global.__FIXED_NOW_MS = fixture.nowMs;
global.__CALENDAR_EVENTS = fixture.events;
const src = fs.readFileSync(codePath, 'utf8');
const fn = new Function(src);
process.stdout.write(JSON.stringify(fn()));
"""


class NodeHarness:
    """Writes the harness/runner/code once, reruns per fixture. No network --
    `node` is invoked as a local subprocess only."""

    def __init__(self, js_code):
        self._tmp = tempfile.mkdtemp(prefix="daily-brief-contract-")
        self.harness_path = os.path.join(self._tmp, "harness.js")
        self.runner_path = os.path.join(self._tmp, "runner.js")
        self.code_path = os.path.join(self._tmp, "assembly.js")
        with open(self.harness_path, "w", encoding="utf-8") as fh:
            fh.write(HARNESS_JS)
        with open(self.runner_path, "w", encoding="utf-8") as fh:
            fh.write(RUNNER_JS)
        with open(self.code_path, "w", encoding="utf-8") as fh:
            fh.write(js_code)

    def run(self, now_ms, events):
        fixture_path = os.path.join(self._tmp, "fixture.json")
        with open(fixture_path, "w", encoding="utf-8") as fh:
            json.dump({"nowMs": now_ms, "events": events}, fh)
        out = subprocess.run(
            ["node", self.runner_path, self.harness_path, fixture_path, self.code_path],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0:
            raise RuntimeError("node fixture run failed: %s" % out.stderr)
        return json.loads(out.stdout)[0]["json"]

    def cleanup(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)


def ev(title, s, e, work_block=False):
    return {"title": title, "startTime": s, "endTime": e, "isAllDay": False,
            "isWorkBlock": work_block, "attendees": []}


harness = NodeHarness(JS_CODE)
try:
    # -------------------------------------------------------------------
    print("B. August 25 exact fixture (occupied=375, free=225, total=600)")
    # -------------------------------------------------------------------
    events = [
        ev("Bradford (trainer)", et_iso(2026, 8, 25, 7, 0), et_iso(2026, 8, 25, 7, 30)),
        ev("Block 1", et_iso(2026, 8, 25, 8, 0), et_iso(2026, 8, 25, 9, 0)),
        ev("Block 2", et_iso(2026, 8, 25, 9, 0), et_iso(2026, 8, 25, 9, 30)),
        ev("Triple A", et_iso(2026, 8, 25, 10, 0), et_iso(2026, 8, 25, 11, 0)),
        ev("Triple B", et_iso(2026, 8, 25, 10, 0), et_iso(2026, 8, 25, 11, 0)),
        ev("Triple C", et_iso(2026, 8, 25, 10, 0), et_iso(2026, 8, 25, 11, 0)),
        ev("Block 3", et_iso(2026, 8, 25, 11, 30), et_iso(2026, 8, 25, 12, 0)),
        ev("MCM Call", et_iso(2026, 8, 25, 13, 0), et_iso(2026, 8, 25, 13, 30)),
        ev("Workshop", et_iso(2026, 8, 25, 14, 0), et_iso(2026, 8, 25, 16, 45)),
        ev("Evening Review", et_iso(2026, 8, 25, 19, 0), et_iso(2026, 8, 25, 19, 30)),
    ]
    r = harness.run(et_ms(2026, 8, 25, 7, 50), events)
    check(r["metrics"]["meetingCount"] == 10, "10 calendar entries counted")
    check("6h15m occupied" in r["atAGlance"], "glance: 6h15m occupied (375 min)")
    check("3h45m open (8" in r["atAGlance"], "glance: 3h45m open (225 min)")
    check("10 calendar entries" in r["atAGlance"], "glance: 'calendar entries', not 'meetings'")
    m = __import__("re").search(r"## Today's Capacity\n(.*?)\n(?:- Largest|- No free|\n)", r["briefMarkdown"], __import__("re").S)
    check(m is not None and "6h15m occupied" in m.group(1) and "3h45m open (8" in m.group(1),
          "Today's Capacity section: one denominator, integer minutes")
    outside = [l for l in r["briefMarkdown"].split("\n") if "Outside the window" in l]
    check(len(outside) == 2, "before-window and after-window entries both surfaced separately: %r" % outside)
    check(r["metrics"]["occupiedMinutes"] == 375 and r["metrics"]["freeMinutes"] == 225,
          "persisted exact integer-minute metrics: occupied=375, free=225")

    # -------------------------------------------------------------------
    print("C. before-window-only and after-window-only meetings")
    # -------------------------------------------------------------------
    r = harness.run(et_ms(2026, 8, 25, 7, 50), [
        ev("Early call", et_iso(2026, 8, 25, 6, 0), et_iso(2026, 8, 25, 7, 0)),
    ])
    check(r["metrics"]["meetingCount"] == 1 and "0h0m occupied" in r["atAGlance"],
          "before-window meeting does not count as occupied")
    check("10h0m open" in r["atAGlance"], "before-window meeting leaves the full window free")
    r = harness.run(et_ms(2026, 8, 25, 7, 50), [
        ev("Late call", et_iso(2026, 8, 25, 19, 0), et_iso(2026, 8, 25, 20, 0)),
    ])
    check("0h0m occupied" in r["atAGlance"] and "10h0m open" in r["atAGlance"],
          "after-window meeting does not count as occupied")

    # -------------------------------------------------------------------
    print("D. multi-day event clamped to today only")
    # -------------------------------------------------------------------
    r = harness.run(et_ms(2026, 8, 25, 7, 50), [
        ev("Trip", et_iso(2026, 8, 24, 18, 0), et_iso(2026, 8, 26, 10, 0)),
    ])
    check("10h0m occupied" in r["atAGlance"], "a trip spanning the whole window clamps to exactly the window (600 min)")
    check("multi-day event on the calendar" in r["briefMarkdown"], "multi-day note rendered")
    check("**Multi-day**" in r["briefMarkdown"], "multi-day event labeled, not printed with a bare cross-day time")

    # -------------------------------------------------------------------
    print("E. DST — both transition days still resolve an exact 600-minute window")
    # -------------------------------------------------------------------
    for label, (y, mo, d) in (("spring-forward", (2026, 3, 8)), ("fall-back", (2026, 11, 1))):
        r = harness.run(et_ms(y, mo, d, 7, 50), [
            ev("Morning", et_iso(y, mo, d, 9, 0), et_iso(y, mo, d, 10, 0)),
            ev("Afternoon", et_iso(y, mo, d, 14, 0), et_iso(y, mo, d, 15, 30)),
        ])
        check("2h30m occupied" in r["atAGlance"] and "7h30m open" in r["atAGlance"],
              "%s: 90 min booked, window still exactly 600 min (90+450)" % label)
        check(r["metrics"]["occupiedMinutes"] + r["metrics"]["freeMinutes"] == 600,
              "%s: persisted integer minutes still sum to exactly 600" % label)

    # -------------------------------------------------------------------
    print("F. largest free gap, integer minutes")
    # -------------------------------------------------------------------
    r = harness.run(et_ms(2026, 8, 25, 7, 50), [
        ev("Morning", et_iso(2026, 8, 25, 8, 0), et_iso(2026, 8, 25, 9, 0)),
        ev("Afternoon", et_iso(2026, 8, 25, 16, 0), et_iso(2026, 8, 25, 17, 0)),
    ])
    check(r["metrics"]["largestFreeBlockMin"] == 420,
          "largest gap (9am-4pm = 420 min) computed as an exact integer: %r" % r["metrics"]["largestFreeBlockMin"])

    # -------------------------------------------------------------------
    print("G. clear calendar (zero events)")
    # -------------------------------------------------------------------
    r = harness.run(et_ms(2026, 8, 25, 7, 50), [])
    check("0h0m occupied" in r["atAGlance"] and "10h0m open" in r["atAGlance"] and "0 calendar entries" in r["atAGlance"],
          "zero events: 0 occupied, full window free, 0 calendar entries")
    check(r["metrics"]["occupiedMinutes"] == 0 and r["metrics"]["freeMinutes"] == 600,
          "zero events: persisted integer minutes are 0 and 600")

    # -------------------------------------------------------------------
    print("H. persisted meeting/free metrics share one denominator (round 2)")
    # -------------------------------------------------------------------
    # Re-use the August 25 fixture: before round 2, metrics.meetingHours was a
    # WHOLE-DAY number (7.3) while metrics.freeHours was WINDOW-ONLY (3.7/3.8)
    # -- the same defect the rendered headline had, one layer down in the
    # persisted trend row (cos_brief_metrics). Both must now derive from the
    # same occupied/free window split.
    r = harness.run(et_ms(2026, 8, 25, 7, 50), events)
    check(r["metrics"]["meetingHours"] == 6.3,
          "metrics.meetingHours is now WINDOW-based (6.3h, matching the headline's 6h15m), "
          "not the old whole-day 7.3h: %r" % r["metrics"]["meetingHours"])
    check(abs(r["metrics"]["meetingHours"] * 60 - r["metrics"]["occupiedMinutes"]) <= 3,
          "legacy meetingHours and exact occupiedMinutes agree to within rounding")
    check(r["metrics"]["occupiedMinutes"] + r["metrics"]["freeMinutes"] == 600,
          "exact integer-minute metrics sum coherently to the full window (600), always")
finally:
    harness.cleanup()

print()
if FAILS:
    print("FAILED: {} check(s):".format(len(FAILS)))
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("OK: all checks passed")
