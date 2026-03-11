// === DETERMINISTIC ASSEMBLY v3.1 ===
// All $() calls must be at top level — n8n Code v2 sandbox restriction.
// No helper functions that reference $().

// --- Safe data gathering (all top-level) ---
var calendar, agendas, myTasks, weeklyGoals, kendraTasks, tylerTasks, othersTasks, notifDoc, newsDoc, emails;

try { calendar = $('Format Calendar').all().map(i => i.json); } catch(e) { calendar = []; }
try { agendas = ($('Format Agendas').first().json || {}).agendas || []; } catch(e) { agendas = []; }
try { myTasks = ($('Categorize My Tasks').first().json || {}).myTasks || {}; } catch(e) { myTasks = {}; }
try { weeklyGoals = ($('Parse Weekly Goals').first().json || {}).weeklyGoals || null; } catch(e) { weeklyGoals = null; }
try { kendraTasks = ($('Format Kendra').first().json || {}).kendraTasks || []; } catch(e) { kendraTasks = []; }
try { tylerTasks = ($('Format Tyler').first().json || {}).tylerTasks || []; } catch(e) { tylerTasks = []; }
try { othersTasks = ($('Filter to Others').first().json || {}).othersTasks || []; } catch(e) { othersTasks = []; }
try { notifDoc = ($('Format Notif Doc').first().json || {}).notificationDoc || null; } catch(e) { notifDoc = null; }
try { newsDoc = ($('Format News Doc').first().json || {}).newsBriefDoc || null; } catch(e) { newsDoc = null; }
try { emails = ($('Filter & Format Emails').first().json || {}).emails || {}; } catch(e) { emails = {}; }

const today = DateTime.now().setZone('America/New_York');
const dateStr = today.toFormat('yyyy-MM-dd');
const dateFmt = today.toFormat('MMMM d, yyyy');
const dayOfWeek = today.toFormat('EEEE');
const isMonday = dayOfWeek === 'Monday';
const dayOfMonth = today.day;
const isFirstMonday = isMonday && dayOfMonth <= 7;
const isoWeek = 'W' + String(today.weekNumber).padStart(2, '0');
const isoYear = today.toFormat('kkkk');

var md = '# Daily Brief \u2014 ' + dateFmt + ', ' + dayOfWeek + '\n\n';

// --- Brief mode ---
if (isFirstMonday) {
  md += '> **Mode: Month-Start Monday** \u2014 extended brief with monthly review trigger\n\n';
} else if (isMonday) {
  md += '> **Mode: Monday** \u2014 week ahead preview included\n\n';
}

// --- COS Assessment placeholder (AI Agent fills this) ---
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
    md += '- **' + time + (endTime ? '\u2013' + endTime : '') + '** ' + e.title;
    if (names) md += ' (' + names + ')';
    md += agendaLink + '\n';
  }
  md += '\n';
}

// --- Capacity ---
var meetingMinutes = 0;
for (var cmi = 0; cmi < dedupedMeetings.length; cmi++) {
  var ev = dedupedMeetings[cmi];
  if (ev.startTime && ev.endTime) {
    meetingMinutes += (new Date(ev.endTime) - new Date(ev.startTime)) / 60000;
  }
}
var meetingHours = Math.round(meetingMinutes / 60 * 10) / 10;
var workWindowHours = 10;
var freeHours = Math.max(0, Math.round((workWindowHours - meetingHours) * 10) / 10);

var workStart = new Date(); workStart.setHours(8, 0, 0, 0);
var workEnd = new Date(); workEnd.setHours(18, 0, 0, 0);
var maxGapMin = 0;
var maxGapStart = workStart;
var maxGapEnd = workEnd;
var prevEnd = workStart;
for (var gi = 0; gi < dedupedMeetings.length; gi++) {
  var s = new Date(dedupedMeetings[gi].startTime);
  var en = new Date(dedupedMeetings[gi].endTime);
  var gap = (s - prevEnd) / 60000;
  if (gap > maxGapMin) { maxGapMin = gap; maxGapStart = prevEnd; maxGapEnd = s; }
  if (en > prevEnd) prevEnd = en;
}
var finalGap = (workEnd - prevEnd) / 60000;
if (finalGap > maxGapMin) { maxGapMin = finalGap; maxGapStart = prevEnd; maxGapEnd = workEnd; }

var fmtT = function(d) { return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }); };

md += "## Today's Capacity\n";
md += '- **' + dedupedMeetings.length + '** meetings (' + meetingHours + ' hours)\n';
md += '- **' + freeHours + '** hours free (8 AM \u2013 6 PM work window)\n';
if (maxGapMin >= 30) {
  md += '- Largest free block: ' + fmtT(maxGapStart) + ' \u2013 ' + fmtT(maxGapEnd) + ' (' + Math.round(maxGapMin / 60 * 10) / 10 + ' hours)\n';
}
if (workBlocks.length > 0) {
  md += '- **Work blocks** (Reclaim): ';
  var wbParts = [];
  for (var wi = 0; wi < workBlocks.length; wi++) {
    var wb = workBlocks[wi];
    var wt = wb.startTime ? new Date(wb.startTime).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }) : '';
    wbParts.push(wb.title + (wt ? ' (' + wt + ')' : ''));
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

md += '**Due Today:**\n';
if (dueToday.length === 0) { md += 'None\n\n'; }
else {
  for (var di = 0; di < dueToday.length; di++) { var t = dueToday[di]; md += '- ' + t.name + ' \u2014 ' + t.list + ' \u2014 [ClickUp](https://app.clickup.com/t/' + t.taskId + ')\n'; }
  md += '\n';
}

md += '**Overdue:**\n';
if (overdue.length === 0) { md += 'None\n\n'; }
else {
  for (var oi = 0; oi < overdue.length; oi++) { var t = overdue[oi]; md += '- ' + t.name + ' \u2014 ' + t.daysOverdue + ' days overdue \u2014 [ClickUp](https://app.clickup.com/t/' + t.taskId + ')\n'; }
  md += '\n';
}

md += '**Possible Today** (upcoming 1-3 days):\n';
if (upcoming.length === 0) { md += 'None\n\n'; }
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

md += '**Needs Reply:**\n';
if (nr.length === 0) { md += 'None\n\n'; }
else {
  for (var ni = 0; ni < nr.length; ni++) { var e = nr[ni]; md += '- ' + e.subject + ' \u2014 from ' + e.from + ' \u2014 ' + e.age + ' \u2014 [Missive](' + e.missiveUrl + ')\n'; }
  md += '\n';
}

md += '**To-Do:**\n';
if (td.length === 0) { md += 'None\n\n'; }
else {
  for (var ti = 0; ti < td.length; ti++) { var e = td[ti]; md += '- ' + e.subject + ' \u2014 [Missive](' + e.missiveUrl + ')\n'; }
  md += '\n';
}

md += '**Possibly Missed:**\n';
if (pm.length === 0) { md += 'None\n\n'; }
else {
  for (var pi = 0; pi < pm.length; pi++) { var e = pm[pi]; md += '- ' + e.subject + ' \u2014 from ' + e.from + ' \u2014 [Missive](' + e.missiveUrl + ')\n'; }
  md += '\n';
}

// --- Team ---
md += '## Team Accountability\n\n';

md += '**Kendra (EA):**\n';
if (kendraTasks.length === 0) { md += 'No tasks due today.\n\n'; }
else {
  for (var ki = 0; ki < kendraTasks.length; ki++) { var t = kendraTasks[ki]; md += '- [ ] ' + t.name + ' \u2014 ' + t.list + ' \u2014 [ClickUp](https://app.clickup.com/t/' + t.taskId + ')\n'; }
  md += '\n';
}

md += '**Tyler (Home Manager):**\n';
if (tylerTasks.length === 0) { md += 'No tasks due today.\n\n'; }
else {
  for (var tyi = 0; tyi < tylerTasks.length; tyi++) { var t = tylerTasks[tyi]; md += '- [ ] ' + t.name + ' \u2014 [ClickUp](https://app.clickup.com/t/' + t.taskId + ')\n'; }
  md += '\n';
}

md += '**Others \u2014 Due Within 3 Days:**\n';
if (othersTasks.length === 0) { md += 'None\n\n'; }
else {
  for (var oti = 0; oti < othersTasks.length; oti++) { var t = othersTasks[oti]; md += '- [ ] ' + t.name + ' \u2014 assigned to ' + (t.assignees || []).join(', ') + ' \u2014 due ' + t.dueDateFormatted + ' \u2014 [ClickUp](https://app.clickup.com/t/' + t.taskId + ')\n'; }
  md += '\n';
}

// --- Monday: Week Ahead Preview placeholder ---
if (isMonday) {
  md += '## Week Ahead Preview\n\n';
  md += '*The AI Agent will synthesize the week ahead based on calendar, sprint goals, and quarterly bets.*\n\n';
}

// --- First Monday: Month-Start Review trigger ---
if (isFirstMonday) {
  md += '## Month-Start Review\n\n';
  md += '\u2192 **Trigger month-start review skill** in morning Claude Code session.\n';
  md += '\u2192 Review quarterly bets, monthly targets, pattern trends, and AHB pipeline progress.\n\n';
}

// --- Metrics ---
var now = Date.now() / 1000;
var oldThreshold = 48 * 3600;
var oldEmails = [];
for (var oei = 0; oei < nr.length; oei++) {
  if (nr[oei].receivedAt && (now - nr[oei].receivedAt) > oldThreshold) oldEmails.push(nr[oei]);
}

return [{
  json: {
    date: dateStr,
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
      meetingHours: meetingHours,
      freeHours: freeHours,
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
