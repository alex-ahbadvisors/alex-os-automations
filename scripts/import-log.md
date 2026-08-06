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
