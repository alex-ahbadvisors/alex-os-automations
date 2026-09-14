# CRM capture identity and review authority

## State of this package

This is a separate CRM repair, discovered during E2. It is not an E2 allowance or
approval. The seven-file source package is prepared for independent review and
human merge/deployment approval. **No live n8n import/deactivation, SQL deployment,
synthetic live write, or additional historical reconciliation is performed here.**

The 833 approved historical review decisions are outside this change. The reviewed
weekly reconciler remains the review writer at the existing Monday 08:07
America/New_York schedule. This does not provide instant ClickUp synchronization.
The reverse workflow source is inactive; all nine old nodes remain intact for
history. An inactive JSON field does not prove the deployed workflow is inactive.

Implementation/review receipts are kept outside source, under:
`~/alex-os-outbox/build-runs/357-2026-09-06-01a074b6/crm-recovery-coordination-2026-09-13/n8n-approved-20260914/`.
A reviewer verdict binds the exact committed candidate hash. Record later review,
merge and deployment receipts there without amending the reviewed source merely
to record a verdict. The parent task coordinates at most two native Claude Max
reviews and one bounded repair; no automatic retry after incomplete output.

## Identity contract

Only exact trimmed, lowercased email addresses in `contacts.emails` count as
identity evidence. Existing email aliases count; name aliases, names, plus/dot
rewriting and inferred shared-mailbox ownership do not. The lookup follows
existing `merged_into` redirects, at most 100 contacts. It does not merge or edit
contacts. It returns every direct owner and its terminal status/version/path in a
single scalar JSON envelope, so an API row limit cannot hide another owner.

- One canonical owner: reuse its ID, including kept or deleted contacts. Never
  write its review status or tier.
- No owner: insert one unscreened `missive-auto` contact once. Unrecognized role
  mailboxes such as `support@...` are held; an already known mailbox may be reused.
- More than one canonical owner, a missing/cyclic/overlong redirect, or a merged
  row with no target: hold that participant and report a system exception.
- Malformed/incomplete lookup responses, invalid input or permission errors:
  hold, never reinterpret the failure as an empty identity set.

`crm_lookup_email_identities(text[])` is STABLE and SECURITY INVOKER, with a fixed
`pg_catalog, public` search path. It grants EXECUTE only to the existing
`service_role` (and the function owner), revokes PUBLIC/anon/authenticated, and
changes no table grants or RLS. It accepts at most 1,000 requested addresses. The
trim set matches JavaScript whitespace, including vertical tab, NBSP and BOM.
The literal PostgreSQL escape `\v` must not be used: it means letter `v`.

The INSERT guard remains a separate, already reviewed deployment dependency:
`alex-os/scripts/docs/crm-contact-insert-guard.sql`. This package does not modify
it. A lookup alone cannot serialize racing creates. The guard serializes INSERT
email claims; it does not provide a general email-UPDATE/merge concurrency lock.

## Capture flow and error visibility

Keep workflow `settings.executionOrder` exactly `v1`. The four outgoing branches
of **Create Interaction** must remain in this top-to-bottom canvas order:

1. **Participants** (y=448): normalize/deduplicate participants, look up owners,
   resolve, and attempt explicit zero-owner creates. The If true output ends for
   known/held participants; its false output creates once and ends.
2. **Merge Participants** (y=624): despite its retained name, this is now a Code
   gate, not a conditional two-input Merge. After the first branch finishes, it
   triggers one fresh lookup for all original participants, constructs valid
   junctions and writes them. Zero participants ends this branch cleanly.
3. **Build Attachments** (y=752): the existing attachment nodes and connections
   are unchanged, including the legitimate zero-attachment case.
4. **Report Capture Identity Exceptions** (y=1200): inspect the resolution bundle
   and junction receipts; throw one named `crm_capture_identity_exception` if
   anything remains unresolved or unverified. Successful links and attachment
   work have already completed. The outward error contains indexes/reason codes,
   not email addresses, message bodies or raw HTTP requests.

n8n's documented v1 behavior completes each branch before the next, using canvas
position. Moving these branch roots or changing execution order changes behavior;
the source tests assert both. See [n8n execution order](https://docs.n8n.io/build/flow-logic/understand-execution-order).
There is no full local n8n engine in this test environment. The tests execute the
actual node JavaScript and expressions and validate graph structure; they model
the documented scheduler. **A supervised deployed-engine smoke remains a gate.**

The HTTP create node includes status and body, sets Never Error, disables node
retries and redirects, and has a 30-second timeout. Continue-on-error only carries
a transport error to the later verifier; it is not permission to ignore it.
[HTTP response options](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest)
explain the distinction between a non-2xx envelope and a transport failure.

The exact `CRM01` plus `crm_known_email_identity:` error is recognized regardless
of whether its HTTP status is 400, 409 or 500. It is never treated as a generic409
skip or a retryable5xx. A fresh lookup must yield exactly one safe owner before a
link is written. Otherwise a visible exception remains. A generic rejection or
unknown write outcome stays exceptional even if the fresh read finds a safe owner
and permits its junction. No second INSERT is attempted. A lost response may
still mean the first INSERT committed; inspect before retrying.

The recheck resolves each original participant explicitly. Successful IDs are
deduplicated per interaction, and all email matches are labeled `email`, including
new contacts. Held participants remain visible in the **Build Junction Rows**
`exceptions` bundle instead of disappearing from output silently.

## Operator handling

Open the failed saved execution. Read **Build Junction Rows** and use its
participant indexes to find the original **Participants** entries. Review the
initial and fresh lookup paths/status/version, and the relevant create result.
The final error is capped to the first 20 reason entries; the execution bundle
retains the complete list. Do not forward raw execution data or credentials to a
reviewer. There is no new approval task, queue, table, schedule or outbound message.

For ambiguity or a broken merge, resolve the existing identity through the
established operator process; never choose an arbitrary owner or insert another
pending contact. For an unknown outcome, read the current identity again before
considering any write. The original interaction and successful links/attachments
remain. Whole-workflow replay is **not** a general repair procedure: existing
interaction uniqueness can stop replay, and already completed side effects must
not be repeated. A separately authorized targeted repair must reuse the existing
interaction, inspect existing junctions, and add only verified missing links.
This package adds no general replay/idempotency engine.

## Supervised deployment gate and order

After independent review and human merge/deployment approval:

1. Export both complete live workflows privately, including active/version state,
   and compare against the preflight bindings below. Check for intervening edits.
   Keep raw exports out of model review; capture exports may contain private
   pinned messages. Preserve backups and current function/trigger definitions.
2. Deactivate the old reverse workflow and verify the actual deployed active
   state. Keep the weekly reconciler and its durable journal. Do not partially
   edit or automatically reactivate the legacy reverse writer.
3. Pause capture for the coordinated change and let in-flight executions settle.
   Install the read-only lookup, verify its signature/ACL/search path and existing
   service credential privileges. Import the reviewed capture while paused, bind
   the existing credentials, and verify the four branch positions plus v1.
4. Apply the separately reviewed INSERT guard only with the compatible caller in
   place. Verify its trigger, body hash, transaction-isolation assumptions and
   actual HTTP CRM01 response. The new guard is not deployed by these instructions
   automatically; approval and exact source/readback checks remain required.
5. Run an explicitly approved, clearly labeled synthetic deployed-engine smoke:
   all-known, all-new, mixed, zero participants, zero attachments, kept/deleted
   reuse, ambiguity, a competing create, CRM01 and transport uncertainty. Verify
   error visibility only after other work finishes, one identity, retained review
   decisions, no new duplicate pending task, and expected junctions/attachments.
   No real-person test record or outbound email. Clean up approved synthetic data.
6. Activate capture only after those checks pass. Record exact imported/exported
   hashes, active/version readbacks, SQL/trigger receipts, smoke evidence and
   cleanup in the outbox receipt directory. A merged PR alone is not deployment.

Preflight exports (2026-09-14 UTC; all nodes/connections/settings matched source):

| Workflow | ID | Version | Private export SHA256 |
|---|---|---|---|
| Capture | `Yu2LOoEaI8ozTrgo` | `08e7b18d-f454-4fbd-bcd3-38bd0a161127` | `ed78eb67195650efea94552a8129da7f7364216f70ee795f217f00fdcdb87a05` |
| Reverse | `5O85So5XAkqyInnJ` | `17c08288-37bc-4b89-8712-5b6f89665a92` | `3763a8f146d3e0456074c7fd5b5c024fd505dbae560b9549e29d16262c060db8` |

These are preflight bindings, not claims about a later live version. Re-export
before deployment. The download menu did not expose `activeVersionId`.

## Rollback

Compare later edits before restoring the private capture backup. Disable/drop the
INSERT guard **before** restoring an incompatible old caller, then restore/drop
only the new read-only lookup as appropriate. Preserve successful contact/link/
attachment records and receipts; this is not data rollback. Keep the reviewed
weekly review path and journal active. Do not reactivate the old reverse writer
as an automatic rollback step. The historical833 decisions are not rolled back.

## Local verification

Run `python3 scripts/tests/test-crm-capture-identity.py`, and both workflow files
through `scripts/validate-n8n.py`. Node is required. The source checks also compare
unrelated nodes/connections and the complete reverse graph against base
`2862c9c15bd4e9acc2a4df8ce173c162476820d6`.

For real synthetic PostgreSQL, run the test with `--postgres`, optionally adding
`--insert-guard /path/to/alex-os/scripts/docs/crm-contact-insert-guard.sql`. The
optional guard is SHA256-bound in the runner. Docker uses only the preinstalled
pinned PostgreSQL16 image, no pull, no network, no published ports or host mounts,
and removes the container in `finally`. Tests verify invoker permissions/RLS,
lookup immutability, all owner paths, more than1,000 owners in a scalar result,
concurrent INSERT/read snapshots and unique junctions. Without the guard they
prove both racing owners remain visible; with it they prove the second claim is
refused and the fresh lookup resolves one owner. These are not live SQL tests.
