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
