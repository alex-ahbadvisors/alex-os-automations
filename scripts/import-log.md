# n8n Import Log

> Append-only record of every workflow validation + import.
> After each import: log what the validator caught, what it missed, and any new patterns discovered.
> This feeds back into `n8n-failure-patterns.md` to make the system smarter.

---

<!-- Template for new entries:

## [Workflow Name] — [Date]

- **JSON file**: `n8n-workflows/filename.json`
- **Validator version**: X patterns checked
- **Issues caught by validator**:
  - [P00X] Description of what was flagged
- **Issues missed by validator (found during testing)**:
  - Description → Added as P00X to failure-patterns.md
- **New patterns discovered**:
  - [P00X] Brief description
- **Debug rounds**: X (before validator) / X (after validator)
- **Notes**:

-->

## Capture Email → Contacts (normalized rebuild + attachments) — 2026-06-04

- **JSON file**: `~/alex-os-inbox/Capture Email Contacts CORRECTED.json` (n8n id `Yu2LOoEaI8ozTrgo`). Spec: `alex-os/plans/2026-06-04-crm-normalized-interactions-attachments.md`.
- **Validator version**: 13 patterns (P001–P013).
- **Issues caught by validator** (before any test — saved rounds):
  - [P003] `Build Junction Rows` convergence fired once per arriving branch (`If` + `Create Contacts`) → fixed with a Merge + `alwaysOutputData`.
  - [P001] `If`/`Create Contacts` and later `Save to Drive`/`Extract from File` feeding a Merge lacked `alwaysOutputData` → added.
  - [P011] (medium) cross-ref past the `Match Contact` HTTP node — assessed as false positive (uses `.all()`/`.first()`, not `.item`).
- **Issues MISSED by validator (found during live testing — ~3 debug rounds)**:
  - Binary dropped: `Save to Drive` chained after `Extract from File` → "no binary field 'data'". → **new P014**.
  - `$('Extract from File').item` on a sibling branch → "No path back to referenced node". Fixed with a `.all()` index-zip Code node (`Assemble Attachment Rows`). → **new P015**.
  - Missive attachment MIME split (`media_type`=`application`, `sub_type`=`pdf`) → `media_type==='application/pdf'` matched 0 of 4 PDFs. → **added to P006**.
  - Contactless-email dedup gap: the old `(contact_id, email_message_id)` unique index never fires once `contact_id` is NULL (NULLs distinct) → duplicate interactions. Fixed with `uniq_missive_email` on `(metadata->>'email_message_id')`. *(schema, not an n8n-node pattern — noted in the canonical spec DDL.)*
  - n8n Cloud Code-node **task-runner timeout** ("not matched to a runner") — transient infra, cleared on retry. Not a workflow defect.
- **New patterns discovered**: P014 (binary-consuming node drops binary in series), P015 (`.item` across branches / post-transform → no path back; use `.all()` zip).
- **Debug rounds**: ~3 (all in the attachment binary/zip area the validator didn't cover). The validator prevented the convergence rounds entirely.
- **Notes**: Verified end-to-end — 4-PDF email → 1 contactless interaction + 4 `attachments` rows (Drive links + 3K–98K chars extracted). TODO: teach `validate-n8n.py` P014 (binary-consumer-in-series) + P015 (sibling-branch `.item`) so the next file build catches them pre-test. Lessons also in memory `reference_n8n_migration_patterns`.

---

## [8] Daily Brief — strip in-flow AI synthesis (the hybrid cutover) — 2026-08-06

- **JSON file**: `relay-migration/8-daily-brief-MODIFIED.json` (n8n `[8] Daily Brief`). Spec: `alex-os/plans/dated/2026-08-05-daily-brief-augmentation-prd.md` (owner-approved improve task `95b4ddf9`).
- **Change**: the flow now runs **no LLM at all**. It gathers deterministically, assembles, and distributes; the judgment layer moved to Athena's `executive-brief` job, which augments the committed `briefs/YYYY-MM-DD/cos-brief.md` locally at ~7:55 ET (flat-rate Max, full alex-os context) instead of n8n paying the metered Anthropic API for a blinder second opinion.
- **Nodes removed (15)**: `AI Agent`, `Anthropic Chat Model` (`claude-opus-4-6`, 2048 max tokens — the metered call), `Daily Brief Prompt` (ClickUp doc `868hqzpqw`), `Structure Agent Input`, `Merge GitHub "Context"with Deterministic Data`, `Convert base64 to text`, `Merge GitHub Files`, and the seven GitHub context fetches (`CLAUDE.md`, `COS-soul.md`, `patterns.md`, `goals.md`, `mission+vision+values.md`, `Sprint`, `Sprint Week Code`, `morning brief skill`). Every one existed only to build the agent's prompt or consume its output — leaving them would have meant 8 orphaned API calls per weekday feeding nothing.
- **Nodes kept, unchanged**: the whole deterministic gather (GCal, ClickUp ×5, Missive ×3, GDrive ×2, weekly goals), `Wait for All Data`, and all five outputs (Missive email, ClickUp task `901113252145`, GDrive doc, GSheet row, `Commit brief to alex-wiki` → `briefs/{{date}}/cos-brief.md`).
- **Nodes edited (2)**:
  - `Deterministic Assembly` — retargeted the two AI-Agent references (placeholder comment + the Monday week-ahead line, which now names Athena), and added a **Source Health** footer: one deterministic line per feed, computed from data already in scope, zero extra API calls. Green means the upstream node *resolved* (zero rows is a legitimate answer on a clear day); red means the branch never produced output. With no LLM left to narrate a missing source in prose, this is what makes the 6/29-class silent break visible.
  - `Build Metadata` — kept as the splice point, but swaps `[COS_ASSESSMENT]` for a pending-judgment notice plus the `<!-- ATHENA_JUDGMENT_LAYER_PENDING -->` marker that `alex-os/scripts/brief-augment.py` keys on. The notice tells the reader, in the brief itself, that the data is complete and unenriched — a raw base can never be mistaken for a finished brief.
- **Rewiring**: `Deterministic Assembly → Build Metadata` directly (was: → Merge GitHub "Context" → Structure Agent Input → Daily Brief Prompt → AI Agent → Build Metadata).
- **Validator**: 13 patterns. **Before: 9 high, 4 medium. After: 0 high, 4 medium.** All 9 high-severity [P001] findings were missing `alwaysOutputData` on feeders into the two AI-context Merge nodes — removing the subtree removed the findings with it, rather than papering over them. The 4 medium are pre-existing and unchanged by this edit: three [P011] cross-reference warnings (assessed as false positives — the Code nodes use `.first()`, not `.item`) and one [P013] Drive-upload retry note (single-item upload, not a bulk path).
- **Testing before handoff** (no n8n import yet — that's Alex's manual step): both edited Code nodes were extracted and executed under Node with stub `$()`/`DateTime` shims, across three fixtures — all feeds healthy, all feeds dead (every branch throws), and all feeds resolving but empty. Confirmed in each: the node runs, `[COS_ASSESSMENT]` is always spliced (no placeholder can ship raw), the Source Health block renders the right colour, and an empty-but-working feed reads green rather than crying wolf.
- **Debug rounds**: 0 (not yet imported).
- **Notes**: rollback is one step — re-add the `AI Agent` + `Anthropic Chat Model` nodes and restore the old two-line `Build Metadata` replace() from git history. The deterministic base is unchanged throughout, so rollback is never a data migration. The retired prompt lives at `alex-os/agents/chief-of-staff/cos-assessment-prompt.md` (banner-marked) and ClickUp doc `868hqzpqw` is no longer fetched and can be archived.

## [8] Daily Brief — legibility pass: HTML email + markdown structure — 2026-08-06

- **JSON file**: `relay-migration/8-daily-brief-MODIFIED.json`. Follows the hybrid cutover entry above, same import.
- **Root cause of the bad email**: `Missive: Email Brief` shipped `briefMarkdown` straight into `drafts.body`. Missive's body is **HTML**, so `**bold**` rendered as literal asterisks, `[label](url)` as literal brackets, and every newline collapsed into one wall of text. Identical to the bug fixed in `2c` on 2026-08-05 ("Body shipped raw markdown (Missive renders literal ** and -)") — `[8]` never got the same treatment.
- **Node added (1)**: `Render Email HTML`, a Code node between `Collect Artifact URLs` and `Missive: Email Brief`. Converts the markdown to email-safe HTML — h1/h2/h3, bullets (with indented continuation lines folded into the same `<li>`), blockquotes, tables, rules, bold/italic/code, links. No npm (Code nodes have none), no layout tables, and **no background or body-text colours** so the reader's own light/dark handling wins; only structure, spacing and link colour are inline-styled. Escapes first, then applies inline rules, so brief content can never inject markup. Also builds the subject.
- **Node edited — `Missive: Email Brief`**: body is now `$json.briefHtml`; subject is `$json.emailSubject` (`Daily Brief — Mon August 10 · 2 meetings (1.5h) · 8.5h free · 2 overdue`), capped at the three load-bearing counts so mail clients don't truncate it.
- **Node edited — `Deterministic Assembly`**: markdown structure, which improves ClickUp/Obsidian/Drive at the same time, not just email.
  - An **at-a-glance line** under the title (meetings, hours free, overdue, due today, needs reply, goal %) — also the email preview text, so it earns its place twice. Emitted as a placeholder and filled at the end, since the counts don't exist until every section has been built.
  - Bold-paragraph pseudo-headings (`**Due Today:**`) became real `###` headings — nine of them. Bold paragraphs give no outline in Obsidian, no hierarchy in the HTML, and no anchors in ClickUp.
  - Bare `None` became italic, specific empty states (`*Nothing overdue.*`).
  - Calendar rows: `10:00–11:00 AM · Title` (one meridiem when both ends share it), attendees on a muted second line, agenda link on a third — instead of everything crammed into one parenthesised run-on.
- **Node edited — `Build Metadata`**: forwards `atAGlance` so the renderer can build the subject.
- **Validator**: 0 high, 4 medium — unchanged by this pass (the 4 medium are the same pre-existing ones).
- **Testing**: the three-node chain (`Deterministic Assembly` → `Build Metadata` → `Render Email HTML`) executed under Node with stub shims across a full day, an all-feeds-dead day, and a table-bearing input. The output HTML was parsed for well-formedness (124 tags, zero unclosed, zero mismatched) and asserted to contain **no** surviving markdown — no `**`, no `](http`, no `^#`, no HTML comments. 13 anchors, 9 h2, 9 h3, 27 li.
- **Notes**: markdown stays canonical everywhere; the HTML is a rendering built at the last step and used only for the email. Anything writing into the brief writes markdown, never HTML.

## [8] Daily Brief — capacity math rebuilt (three live wrong-number bugs) — 2026-08-06

- **JSON file**: `relay-migration/8-daily-brief-MODIFIED.json`. Same import as the two entries above.
- **Trigger**: Alex read "98 hours free" on a preview. I had called that a test-fixture artifact. It was not — the same class of number ships in production. Reproduced by running the pre-fix `Deterministic Assembly` under `TZ=UTC` (what n8n Cloud runs) against his real 2026-08-06 calendar.
- **Bug 1 — timezone.** The work window was built as `new Date(); setHours(8,0,0,0)` — the **n8n server's** local time. This workflow pins no timezone and n8n Cloud runs UTC, so the window was really **04:00–14:00 ET** while every printed time is ET. On a clear day the old code printed `Largest free block: 4:00 AM – 2:00 PM`. On Alex's 8/6 calendar it printed `Largest free block: 4:30 PM – 9:45 PM (5.3 hours)` — a block that runs past the window's end and straight through the evening.
- **Bug 2 — out-of-window meetings charged to the in-window budget.** `freeHours = 10 − TOTAL meeting hours`. Alex's recurring 9:45–11:00 PM block was subtracted from the 8–6 budget it was never inside: 4.5h free reported where the truth was 6h.
- **Bug 3 — nothing clamped an event to today.** Google Calendar returns events that merely **overlap** the requested range, so a multi-day timed event (a trip, a conference) arrives with a `startTime` days earlier. Old code, two events, one of them a week-long trip: `2 meetings (178 hours)`. That is the "98 hours" Alex saw.
- **Also fixed — double-counted overlaps.** Two meetings sharing a slot (his 10:30–11:15 and 11:00–12:00 on 8/6) were counted twice. Spans are now merged before measuring: a double-booked hour is one hour of his day.
- **Fix**: all arithmetic moved to Luxon in `America/New_York` (`DateTime` is already available in n8n Code nodes; `today` was already zoned). Every event is intersected with today's window before it can influence a number; the window is walked once for merged busy time and the largest true gap; out-of-window meetings and multi-day events are reported on their own lines instead of silently distorting the totals; a multi-day event's row renders as `Multi-day` rather than a plausible-looking time of day belonging to another date.
- **Verified**: the three-node chain executed under **both** `TZ=UTC` and `TZ=America/New_York` with **real Luxon** (not a stub) across Alex's actual 2026-08-06 calendar shape, a multi-day-event day, and a clear day. Output is byte-identical across the two server timezones — the class of bug is structurally gone, not just papered over for one zone. Before/after on his real calendar: free 4.5h → 6h; largest block `4:30 PM–9:45 PM` → `12:00 PM–2:30 PM`; multi-day day `178 hours` → `24h today, 1 multi-day event flagged`.
- **Validator**: 0 high, 4 medium — unchanged.
- **Lesson for the next Code node**: `new Date()` in an n8n Code node is **server-local**, not workflow-local. Anything date-arithmetic-shaped must use `DateTime` (Luxon) with an explicit zone. Adding to `n8n-failure-patterns.md` as a candidate pattern.
