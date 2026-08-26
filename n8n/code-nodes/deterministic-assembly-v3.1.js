// === DETERMINISTIC ASSEMBLY v3.1 ===
// All $() calls must be at top level — n8n Code v2 sandbox restriction.
// No helper functions that reference $().

// --- Safe data gathering (all top-level) ---
var calendar, agendas, myTasks, weeklyGoals, kendraTasks, tylerTasks, othersTasks, notifDoc, newsDoc, emails;

// ok* flags feed the Source Health footer. TRUE means the upstream node
// resolved — including when it legitimately returned nothing (a clear calendar
// is not a broken feed). FALSE means the reference threw: the branch never ran,
// so that section of the brief is untrustworthy, not merely empty.
var okCalendar = false, okAgendas = false, okMyTasks = false, okGoals = false;
var okKendra = false, okTyler = false, okOthers = false;
var okNotif = false, okNews = false, okEmails = false;

try { calendar = $('Format Calendar').all().map(i => i.json); okCalendar = true; } catch(e) { calendar = []; }
try { agendas = ($('Format Agendas').first().json || {}).agendas || []; okAgendas = true; } catch(e) { agendas = []; }
try { myTasks = ($('Categorize My Tasks').first().json || {}).myTasks || {}; okMyTasks = true; } catch(e) { myTasks = {}; }
try { weeklyGoals = ($('Parse Weekly Goals').first().json || {}).weeklyGoals || null; okGoals = true; } catch(e) { weeklyGoals = null; }
try { kendraTasks = ($('Format Kendra').first().json || {}).kendraTasks || []; okKendra = true; } catch(e) { kendraTasks = []; }
try { tylerTasks = ($('Format Tyler').first().json || {}).tylerTasks || []; okTyler = true; } catch(e) { tylerTasks = []; }
try { othersTasks = ($('Filter to Others').first().json || {}).othersTasks || []; okOthers = true; } catch(e) { othersTasks = []; }
try { notifDoc = ($('Format Notif Doc').first().json || {}).notificationDoc || null; okNotif = true; } catch(e) { notifDoc = null; }
try { newsDoc = ($('Format News Doc').first().json || {}).newsBriefDoc || null; okNews = true; } catch(e) { newsDoc = null; }
try { emails = ($('Filter & Format Emails').first().json || {}).emails || {}; okEmails = true; } catch(e) { emails = {}; }

const today = DateTime.now().setZone('America/New_York');
const dateStr = today.toFormat('yyyy-MM-dd');
const dateFmt = today.toFormat('MMMM d, yyyy');
const dayOfWeek = today.toFormat('EEEE');
const isMonday = dayOfWeek === 'Monday';
const dayOfMonth = today.day;
const isFirstMonday = isMonday && dayOfMonth <= 7;
const isoWeek = 'W' + String(today.weekNumber).padStart(2, '0');
const isoYear = today.toFormat('kkkk');

var md = '# Daily Brief \u2014 ' + dayOfWeek + ', ' + dateFmt + '\n\n';
// One scannable line under the title, filled in at the bottom once the
// counts exist. It is also what shows as the email preview text, so it
// earns its place twice.
md += '[AT_A_GLANCE]\n\n';

// --- Brief mode ---
if (isFirstMonday) {
  md += '> **Mode: Month-Start Monday** \u2014 extended brief with monthly review trigger\n\n';
} else if (isMonday) {
  md += '> **Mode: Monday** \u2014 week ahead preview included\n\n';
}

// --- Judgment-layer placeholder ---
// Filled by 'Build Metadata' with the pending-judgment notice. The actual
// judgment (five sections) is written locally by Athena's executive-brief
// job at ~7:55 ET, NOT here. No LLM runs in this flow.
md += '[COS_ASSESSMENT]\n\n';

// --- News & Notifications ---
md += '## News & Notifications\n';
md += '- **Notification Brief** (yesterday): ' + (notifDoc ? '[' + notifDoc.name + '](' + notifDoc.url + ')' : 'Not available') + '\n';
md += '- **News Brief** (today): ' + (newsDoc ? '[' + newsDoc.name + '](' + newsDoc.url + ')' : 'Not available') + '\n\n';

// --- Calendar (sorted by start time) ---
md += "## Today's Calendar\n\n";
var allEvents = calendar.filter(i => !i.isAllDay && i.title);
var meetings = allEvents.filter(i => !i.isWorkBlock);
var workBlocks = allEvents.filter(i => i.isWorkBlock);
var seen = {};
var dedupedMeetings = [];
for (var mi = 0; mi < meetings.length; mi++) {
  var m = meetings[mi];
  var key = m.title + '|' + m.startTime;
  if (!seen[key]) {
    seen[key] = true;
    dedupedMeetings.push(m);
  }
}
dedupedMeetings.sort(function(a, b) { return new Date(a.startTime) - new Date(b.startTime); });

if (dedupedMeetings.length === 0) {
  md += 'Clear calendar \u2014 protect for deep work.\n\n';
} else {
  for (var ci = 0; ci < dedupedMeetings.length; ci++) {
    var e = dedupedMeetings[ci];
    var time = e.startTime ? new Date(e.startTime).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }) : 'TBD';
    var endTime = e.endTime ? new Date(e.endTime).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }) : '';
    var names = (e.attendees || []).map(function(a) { return a.name; }).join(', ') || '';
    var agenda = null;
    for (var ai = 0; ai < agendas.length; ai++) {
      if (e.title.toLowerCase().indexOf(agendas[ai].name.toLowerCase()) >= 0 || agendas[ai].name.toLowerCase().indexOf(e.title.toLowerCase()) >= 0) {
        agenda = agendas[ai];
        break;
      }
    }
    var agendaLink = agenda ? ' \u2014 [Agenda](https://app.clickup.com/t/' + agenda.taskId + ')' : '';
    // '10:00 \u2013 11:00 AM' rather than '10:00 AM \u2013 11:00 AM': one
    // meridiem is enough when both ends share it, and the row scans faster.
    var sameMeridiem = time.slice(-2) === endTime.slice(-2);
    var timeLabel = (sameMeridiem ? time.replace(/ ?[AP]M$/, '') : time) +
                    (endTime ? '\u2013' + endTime : '');
    // A multi-day event's start/end times belong to OTHER days; printing them
    // bare reads as a normal meeting today. Say so instead.
    var evS = new Date(e.startTime).getTime();
    var evE = new Date(e.endTime).getTime();
    var evDayStart = today.startOf('day').toMillis();
    var evDayEnd = today.endOf('day').toMillis();
    if (isFinite(evS) && isFinite(evE) && (evS < evDayStart || evE > evDayEnd)) {
      timeLabel = 'Multi-day';
    }
    md += '- **' + timeLabel + '** \u00b7 ' + e.title;
    if (names) md += '  \n  *' + names + '*';
    md += (agendaLink ? '  \n  ' + agendaLink.replace(' \u2014 ', '') : '') + '\n';
  }
  md += '\n';
}

// --- Capacity (rebuilt 2026-08-06 — three bugs, all of them silent) ---
// 1. The window was built with `new Date().setHours(8)` = the n8n SERVER's
//    local time. n8n Cloud runs UTC and this workflow pins no timezone, so the
//    real window was 4 AM - 2 PM ET while every printed time is ET. The brief
//    offered "free blocks" at 4 AM and stopped the day at 2 PM.
// 2. Free hours were `10 - TOTAL meeting hours`, so a 9:45 PM call was
//    subtracted from an 8-6 budget it was never inside.
// 3. Nothing clamped an event to today. GCal returns events that merely
//    OVERLAP the requested day, so a multi-day timed event (a trip) arrives
//    with a startTime days earlier — which is how a free block of 98 hours
//    gets printed.
// All three are fixed by doing the arithmetic in ET and intersecting every
// event with today before it can influence any number.
var WORK_START_HOUR = 8, WORK_END_HOUR = 18;
var winStart = today.set({ hour: WORK_START_HOUR, minute: 0, second: 0, millisecond: 0 }).toMillis();
var winEnd = today.set({ hour: WORK_END_HOUR, minute: 0, second: 0, millisecond: 0 }).toMillis();
var dayStart = today.startOf('day').toMillis();
var dayEnd = today.endOf('day').toMillis();
var workWindowHours = Math.round((winEnd - winStart) / 3600000 * 10) / 10;

var fmtT = function(ms) {
  return DateTime.fromMillis(ms).setZone('America/New_York').toFormat('h:mm a');
};
var overlapMs = function(aStart, aEnd, bStart, bEnd) {
  return Math.max(0, Math.min(aEnd, bEnd) - Math.max(aStart, bStart));
};
var hrs = function(ms) { return Math.round(ms / 3600000 * 10) / 10; };

// Normalise every meeting to millis, dropping anything unparseable rather than
// letting a bad timestamp poison the arithmetic. Overlapping spans are merged
// below (in the window walk) so a double-booked slot is measured once.
var spans = [];              // clamped to the work window
var outsideWindow = [];      // real meetings, just not between 8 and 6
var spillsPastToday = 0;     // multi-day events, counted only for today
for (var cmi = 0; cmi < dedupedMeetings.length; cmi++) {
  var ev = dedupedMeetings[cmi];
  if (!ev.startTime || !ev.endTime) continue;
  var s = new Date(ev.startTime).getTime();
  var e2 = new Date(ev.endTime).getTime();
  if (!isFinite(s) || !isFinite(e2) || e2 <= s) continue;
  if (s < dayStart || e2 > dayEnd) spillsPastToday++;
  var inWin = overlapMs(s, e2, winStart, winEnd);
  if (inWin > 0) {
    spans.push({ start: Math.max(s, winStart), end: Math.min(e2, winEnd) });
  } else {
    outsideWindow.push({ title: ev.title, start: s, end: e2 });
  }
}
spans.sort(function(a, b) { return a.start - b.start; });

// Walk the window once: merged busy time (double-booked slots must not be
// counted twice) and the largest uninterrupted gap.
var bookedInWindowMs = 0, cursor = winStart;
var maxGapMs = 0, maxGapStart = winStart, maxGapEnd = winStart;
for (var gi = 0; gi < spans.length; gi++) {
  if (spans[gi].start > cursor) {
    var gap = spans[gi].start - cursor;
    if (gap > maxGapMs) { maxGapMs = gap; maxGapStart = cursor; maxGapEnd = spans[gi].start; }
  }
  if (spans[gi].end > cursor) {
    bookedInWindowMs += spans[gi].end - Math.max(cursor, spans[gi].start);
    cursor = spans[gi].end;
  }
}
if (winEnd - cursor > maxGapMs) { maxGapMs = winEnd - cursor; maxGapStart = cursor; maxGapEnd = winEnd; }

// --- Integer-minute ground truth (348B fix, 2026-08-26) ---
// The headline used to pair meetingHours (WHOLE-DAY, includes evening blocks)
// with freeHours (WINDOW-ONLY) on one line — a 10-meeting/7.3h day next to a
// "3.7h free (8-6)" computed against a different budget, implying an 11-hour
// day out of a 10-hour window. freeHours also subtracted two INDEPENDENTLY
// rounded decimals. Round exactly ONCE, from the raw ms, and derive the
// primary headline entirely from that single 08:00-18:00 denominator.
var occupiedMin = Math.round(bookedInWindowMs / 60000);
var windowMin = Math.round((winEnd - winStart) / 60000);
var freeMin = Math.max(0, windowMin - occupiedMin);
// meetingHours/freeHours (legacy decimal-hours pair persisted to
// cos_brief_metrics by Flatten Metrics) must share the SAME window
// denominator as the integer-minute truth above -- a whole-day meetingHours
// next to a window-only freeHours reproduced this exact bug one layer down,
// in the trend store, even after the rendered headline was fixed (round 2
// finding).
var meetingHours = Math.round(occupiedMin / 60 * 10) / 10;
var freeHours = Math.round(freeMin / 60 * 10) / 10;
var maxGapMin = Math.round(maxGapMs / 60000);
var fmtHM = function(min) { return Math.floor(min / 60) + 'h' + (min % 60) + 'm'; };

md += "## Today's Capacity\n";
md += '- **' + fmtHM(occupiedMin) + ' occupied \u00b7 ' + fmtHM(freeMin) + ' open (8\u20136)** \u00b7 ' +
      dedupedMeetings.length + ' calendar ' + (dedupedMeetings.length === 1 ? 'entry' : 'entries') + '\n';
if (maxGapMin >= 30) {
  md += '- Largest free block: **' + fmtT(maxGapStart) + ' – ' + fmtT(maxGapEnd) + '** (' +
        hrs(maxGapMs) + ' hours)\n';
} else if (spans.length > 0) {
  md += '- No free block of 30 minutes or more — today is execution-only.\n';
}
for (var owi = 0; owi < outsideWindow.length; owi++) {
  md += '- *Outside the window:* ' + outsideWindow[owi].title + ' (' +
        fmtT(outsideWindow[owi].start) + ' – ' + fmtT(outsideWindow[owi].end) +
        ') — not counted against free hours\n';
}
if (spillsPastToday > 0) {
  md += '- *' + spillsPastToday + ' multi-day event' + (spillsPastToday === 1 ? '' : 's') +
        ' on the calendar — counted for today only*\n';
}
if (workBlocks.length > 0) {
  md += '- **Work blocks** (Reclaim): ';
  var wbParts = [];
  for (var wi = 0; wi < workBlocks.length; wi++) {
    var wb = workBlocks[wi];
    var wbMs = wb.startTime ? new Date(wb.startTime).getTime() : NaN;
    wbParts.push(wb.title + (isFinite(wbMs) ? ' (' + fmtT(wbMs) + ')' : ''));
  }
  md += wbParts.join(', ');
  md += '\n';
}
md += '\n';

// --- My Action Items ---
var overdue = myTasks.overdue || [];
var dueToday = myTasks.dueToday || [];
var upcoming = myTasks.upcoming || [];

md += '## My Action Items\n\n';

md += '### Due Today\n\n';
if (dueToday.length === 0) { md += '*Nothing due today.*\n\n'; }
else {
  for (var di = 0; di < dueToday.length; di++) { var t = dueToday[di]; md += '- ' + t.name + ' \u2014 ' + t.list + ' \u2014 [ClickUp](https://app.clickup.com/t/' + t.taskId + ')\n'; }
  md += '\n';
}

md += '### Overdue\n\n';
if (overdue.length === 0) { md += '*Nothing overdue.*\n\n'; }
else {
  for (var oi = 0; oi < overdue.length; oi++) { var t = overdue[oi]; md += '- ' + t.name + ' \u2014 ' + t.daysOverdue + ' days overdue \u2014 [ClickUp](https://app.clickup.com/t/' + t.taskId + ')\n'; }
  md += '\n';
}

md += '### Possible Today (next 1\u20133 days)\n\n';
if (upcoming.length === 0) { md += '*Nothing in the next three days.*\n\n'; }
else {
  for (var ui = 0; ui < upcoming.length; ui++) { var t = upcoming[ui]; md += '- ' + t.name + ' \u2014 due ' + t.dueDateFormatted + ' \u2014 [ClickUp](https://app.clickup.com/t/' + t.taskId + ')\n'; }
  md += '\n';
}

// --- Weekly Goals ---
md += '## Weekly Goals\n';
if (!weeklyGoals) {
  md += 'No weekly goals set this week.\n\n';
} else {
  md += '**' + weeklyGoals.taskName + '** \u2014 ' + weeklyGoals.completedItems + ' of ' + weeklyGoals.totalItems + ' complete (' + weeklyGoals.completionPct + '%) \u2014 [ClickUp](https://app.clickup.com/t/' + weeklyGoals.taskId + ')\n';
  for (var wgi = 0; wgi < weeklyGoals.goals.length; wgi++) { var g = weeklyGoals.goals[wgi]; md += '- ' + (g.resolved ? '\u2705' : '\u2b1c') + ' ' + g.name + ' \u2014 ' + g.section + '\n'; }
  md += '\n';
}

// --- Email ---
var nr = emails.needsReply || [];
var td = emails.todo || [];
var pm = emails.possiblyMissed || [];

md += '## Email Attention Needed\n\n';

md += '### Needs Reply\n\n';
if (nr.length === 0) { md += '*Nothing waiting on a reply.*\n\n'; }
else {
  for (var ni = 0; ni < nr.length; ni++) { var e = nr[ni]; md += '- ' + e.subject + ' \u2014 from ' + e.from + ' \u2014 ' + e.age + ' \u2014 [Missive](' + e.missiveUrl + ')\n'; }
  md += '\n';
}

md += '### To-Do\n\n';
if (td.length === 0) { md += '*Empty.*\n\n'; }
else {
  for (var ti = 0; ti < td.length; ti++) { var e = td[ti]; md += '- ' + e.subject + ' \u2014 [Missive](' + e.missiveUrl + ')\n'; }
  md += '\n';
}

md += '### Possibly Missed\n\n';
if (pm.length === 0) { md += '*Nothing flagged.*\n\n'; }
else {
  for (var pi = 0; pi < pm.length; pi++) { var e = pm[pi]; md += '- ' + e.subject + ' \u2014 from ' + e.from + ' \u2014 [Missive](' + e.missiveUrl + ')\n'; }
  md += '\n';
}

// --- Team ---
md += '## Team Accountability\n\n';

md += '### Kendra (EA)\n\n';
if (kendraTasks.length === 0) { md += '*No tasks due today.*\n\n'; }
else {
  for (var ki = 0; ki < kendraTasks.length; ki++) { var t = kendraTasks[ki]; md += '- [ ] ' + t.name + ' \u2014 ' + t.list + ' \u2014 [ClickUp](https://app.clickup.com/t/' + t.taskId + ')\n'; }
  md += '\n';
}

md += '### Tyler (Home Manager)\n\n';
if (tylerTasks.length === 0) { md += '*No tasks due today.*\n\n'; }
else {
  for (var tyi = 0; tyi < tylerTasks.length; tyi++) { var t = tylerTasks[tyi]; md += '- [ ] ' + t.name + ' \u2014 [ClickUp](https://app.clickup.com/t/' + t.taskId + ')\n'; }
  md += '\n';
}

md += '### Others \u2014 due within 3 days\n\n';
if (othersTasks.length === 0) { md += '*Nothing due.*\n\n'; }
else {
  for (var oti = 0; oti < othersTasks.length; oti++) { var t = othersTasks[oti]; md += '- [ ] ' + t.name + ' \u2014 assigned to ' + (t.assignees || []).join(', ') + ' \u2014 due ' + t.dueDateFormatted + ' \u2014 [ClickUp](https://app.clickup.com/t/' + t.taskId + ')\n'; }
  md += '\n';
}

// --- Monday: Week Ahead Preview placeholder ---
if (isMonday) {
  md += '## Week Ahead Preview\n\n';
  md += '*Week-ahead synthesis (calendar, sprint goals, quarterly bets) is added by Athena at ~7:55 ET.*\n\n';
}

// --- First Monday: Month-Start Review trigger ---
if (isFirstMonday) {
  md += '## Month-Start Review\n\n';
  md += '\u2192 **Trigger month-start review skill** in morning Claude Code session.\n';
  md += '\u2192 Review quarterly bets, monthly targets, pattern trends, and AHB pipeline progress.\n\n';
}

// --- Source Health (deterministic freshness stamp) ---
// A silently-broken feed is the failure mode that cost two briefs on 6/29 — and
// with no LLM in this flow, nothing else narrates it. Green = the fetch
// resolved (zero rows is a legitimate answer). Red = the branch never produced
// output, so that section of the brief is untrustworthy, not merely quiet.
// Computed from data already in scope: zero extra API calls.
var plural = function(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); };
var healthRows = [
  ['Calendar (GCal)', okCalendar, plural(calendar.length, 'event')],
  ['Meeting agendas (ClickUp)', okAgendas, plural(agendas.length, 'agenda')],
  ['My tasks (ClickUp)', okMyTasks, plural(overdue.length + dueToday.length + upcoming.length, 'task')],
  ['Weekly goals (ClickUp)', okGoals, weeklyGoals ? weeklyGoals.completionPct + '% complete' : 'none set this week'],
  ['Kendra tasks (ClickUp)', okKendra, plural(kendraTasks.length, 'task')],
  ['Tyler tasks (ClickUp)', okTyler, plural(tylerTasks.length, 'task')],
  ["Others' tasks (ClickUp)", okOthers, plural(othersTasks.length, 'task')],
  ['Email buckets (Missive)', okEmails, plural(nr.length + td.length + pm.length, 'thread')],
  ['News brief (Drive)', okNews, newsDoc ? newsDoc.name : 'no doc found for today'],
  ['Notification brief (Drive)', okNotif, notifDoc ? notifDoc.name : 'no doc found for yesterday']
];
md += '## Source Health\n';
md += '_Deterministic base generated ' + today.toFormat('yyyy-MM-dd HH:mm') + ' ET by n8n `[8]`. No LLM ran in this flow._\n\n';
for (var hi = 0; hi < healthRows.length; hi++) {
  var hr = healthRows[hi];
  md += '- ' + (hr[1] ? '\u2705' : '\uD83D\uDD34') + ' **' + hr[0] + '** \u2014 ' + (hr[1] ? hr[2] : 'FEED DID NOT RUN') + '\n';
}
md += '\n';

// --- Metrics ---
var now = Date.now() / 1000;
var oldThreshold = 48 * 3600;
var oldEmails = [];
for (var oei = 0; oei < nr.length; oei++) {
  if (nr[oei].receivedAt && (now - nr[oei].receivedAt) > oldThreshold) oldEmails.push(nr[oei]);
}

// --- At a glance (the one line that has to survive a phone lock screen) ---
var glance = [];
glance.push(fmtHM(occupiedMin) + ' occupied');
glance.push(fmtHM(freeMin) + ' open (8\u20136)');
glance.push(dedupedMeetings.length + ' calendar ' + (dedupedMeetings.length === 1 ? 'entry' : 'entries'));
if (overdue.length) glance.push('**' + overdue.length + ' overdue**');
if (dueToday.length) glance.push(dueToday.length + ' due today');
if (nr.length) glance.push(nr.length + ' needs reply');
if (weeklyGoals) glance.push('goals ' + weeklyGoals.completionPct + '%');
md = md.replace('[AT_A_GLANCE]', glance.join('  \u00b7  '));

return [{
  json: {
    date: dateStr,
    atAGlance: glance.join(' \u00b7 ').replace(/\*\*/g, ''),
    dateFormatted: dateFmt,
    dayOfWeek: dayOfWeek,
    isMonday: isMonday,
    isFirstMonday: isFirstMonday,
    isoWeek: isoWeek,
    isoYear: isoYear,
    sprintFilePath: 'sprints/' + isoYear + '-' + isoWeek + '.md',
    briefMarkdown: md,
    metrics: {
      meetingCount: dedupedMeetings.length,
      meetingHours: meetingHours,      // legacy decimal-hours (rounded once)
      freeHours: freeHours,            // legacy decimal-hours (rounded once)
      occupiedMinutes: occupiedMin,    // exact integers; always sum to windowMin
      freeMinutes: freeMin,
      largestFreeBlockMin: maxGapMin,
      totalTaskCount: overdue.length + dueToday.length + upcoming.length,
      totalEmailCount: nr.length + td.length + pm.length,
      overdueTaskCount: overdue.length,
      needsReplyCount: nr.length,
      oldEmailCount: oldEmails.length,
      weeklyGoalPct: weeklyGoals ? weeklyGoals.completionPct : 0,
      newsBriefLink: (newsDoc && newsDoc.url) ? newsDoc.url : '',
      notificationBriefLink: (notifDoc && notifDoc.url) ? notifDoc.url : ''
    }
  }
}];
