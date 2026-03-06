# n8n Failure Patterns — Living Knowledge Base

> This file is read by `validate-n8n.py` and updated after every workflow import.
> Each pattern has: ID, name, description, detection logic, fix, and history of when it was caught/missed.
> Add new patterns at the bottom. Never delete — mark as `status: retired` if no longer relevant.

---

## P001: Missing alwaysOutputData on branch nodes

- **Status**: active
- **Severity**: high
- **Category**: convergence
- **Description**: When multiple parallel branches converge on a single downstream node, any branch that produces no output will cause `$('Node Name')` references to throw "hasn't been executed" errors. Every node in a parallel branch needs `alwaysOutputData: true`.
- **Detection**: Find nodes that have 2+ inputs (convergence points). Trace upstream branches. Flag any node in those branches missing `"alwaysOutputData": true` in its options or top-level properties.
- **Fix**: Add `"alwaysOutputData": true` to node options for every node in parallel branches.
- **Discovered**: 2026-03-05, Daily Brief [8] debugging
- **Times caught**: 0
- **Times missed**: 0

---

## P002: ClickUp node defaults to "create" operation

- **Status**: active
- **Severity**: medium
- **Category**: node-defaults
- **Description**: The ClickUp node (v1 and v2) defaults `operation` to `"create"`. If you intend to update a task, you must explicitly set `"operation": "update"`. Forgetting this creates duplicate tasks instead of updating existing ones.
- **Detection**: Find all ClickUp nodes. If the node name or context suggests an update (contains "update", "edit", "modify", or is wired after a "get" node for the same resource), flag if `operation` is `"create"` or missing.
- **Fix**: Set `"operation": "update"` explicitly in node parameters.
- **Discovered**: 2026-03-03, E2 Meeting Agenda Builder
- **Times caught**: 0
- **Times missed**: 0

---

## P003: Parallel execution into single downstream node

- **Status**: active
- **Severity**: high
- **Category**: wiring
- **Description**: n8n fires a downstream node once per arriving input, not after all inputs arrive. Wiring 2+ nodes into the same input causes race conditions and "hasn't been executed" errors. Must wire sequentially or use a Merge/Wait node.
- **Detection**: Find nodes that receive connections from 2+ different source nodes on the same input index. Flag as parallel convergence risk.
- **Fix**: Wire sequentially, or use a Merge node (mode: "Wait for All") before the downstream node.
- **Discovered**: 2026-03-03, E2 Meeting Agenda Builder
- **Times caught**: 0
- **Times missed**: 0

---

## P004: Paired-item reference on synthetic empty items

- **Status**: active
- **Severity**: medium
- **Category**: data-threading
- **Description**: `$('Node').item.json` fails when the upstream node is a DataTable that returned zero rows (synthetic empty item). Use `.first().json` with a null check or `.all()` with index matching instead.
- **Detection**: Find Code nodes that contain `$('`.  If any referenced node is a DataTable or could return empty results, flag usage of `.item.json` (should be `.first()?.json` or `.all()`).
- **Fix**: Replace `.item.json` with `.first()?.json ?? {}` or use `.all()` with explicit index handling.
- **Discovered**: 2026-03-03, E2 Meeting Agenda Builder
- **Times caught**: 0
- **Times missed**: 0

---

## P005: DataTable field name case sensitivity

- **Status**: active
- **Severity**: medium
- **Category**: data-threading
- **Description**: n8n DataTable column names are case-sensitive. `ClickUp_LIst_ID` is not `clickup_list_id`. Mismatched casing causes silent undefined values, not errors.
- **Detection**: Extract all DataTable field references in Code nodes. Cross-reference against actual DataTable column names if available in the workflow JSON. Flag case mismatches.
- **Fix**: Use exact column names. Consider a helper function that checks multiple casing variants.
- **Discovered**: 2026-03-03, E2 Meeting Agenda Builder
- **Times caught**: 0
- **Times missed**: 0

---

## P006: Missive API field gotchas

- **Status**: active
- **Severity**: medium
- **Category**: api-mismatch
- **Description**: Missive API has several underdocumented behaviors: (1) `subject` field is always null — use `latest_message_subject`, (2) `modified_after` param doesn't exist, (3) web URLs differ from API response URLs — use `web_url` field, (4) POST /v1/posts requires BOTH `notification: {title, body}` AND `text`/`markdown` — neither alone is sufficient.
- **Detection**: Find HTTP Request nodes targeting `missiveapp.com`. Flag if: referencing `.subject` without `latest_message_subject`, using `modified_after` param, constructing URLs manually instead of using `web_url`, or POST to `/posts` missing either `notification` or `text/markdown`.
- **Fix**: See `alex-os/skills/n8n-copilot/references/missive-api.md` for correct field mappings.
- **Discovered**: 2026-03-03, 3CV Email Classifier + E2 Meeting Agenda Builder
- **Times caught**: 0
- **Times missed**: 0

---

## P007: ClickUp date filter excludes tasks with no due date

- **Status**: active
- **Severity**: medium
- **Category**: api-mismatch
- **Description**: ClickUp API's `due_date_lt` filter excludes tasks that have no due date — it doesn't treat "no due date" as "due anytime." If most tasks lack due dates, the filter returns empty results.
- **Detection**: Find ClickUp API calls or ClickUp nodes using `due_date_lt` or `due_date_gt` filters. Flag with warning that tasks without due dates will be excluded.
- **Fix**: Remove date filter from API call. Do date bucketing in a downstream Code node instead (overdue/today/upcoming/noDueDate).
- **Discovered**: 2026-03-05, Daily Brief [8] debugging
- **Times caught**: 0
- **Times missed**: 0

---

## P008: Data threading gaps across sub-workflows

- **Status**: active
- **Severity**: high
- **Category**: data-threading
- **Description**: When a downstream sub-workflow (e.g., 7b) needs data from an upstream workflow (7a), every intermediate node must explicitly pass required fields through. One missing passthrough = silent failure where the field is undefined downstream.
- **Detection**: Find Execute Sub-Workflow nodes. Check if the data passed to the sub-workflow includes all fields that the sub-workflow's nodes reference. Flag gaps.
- **Fix**: Ensure every intermediate node explicitly includes required fields in its output. Use a Set node before sub-workflow calls to consolidate needed fields.
- **Discovered**: 2026-03-03, E2 Meeting Agenda Builder
- **Times caught**: 0
- **Times missed**: 0

---

## P009: Missing try-catch on $() references in convergence nodes

- **Status**: active
- **Severity**: high
- **Category**: convergence
- **Description**: Even with `alwaysOutputData: true` on all branch nodes, `$('Node Name')` can still throw if a branch errored or has timing issues. Every `$()` reference in a convergence Code node needs a try-catch wrapper (safeFirst/safeAll pattern).
- **Detection**: Find Code nodes that reference 3+ other nodes via `$('...')`. If the node is a convergence point (receives from multiple branches), flag any `$()` call not wrapped in try-catch.
- **Fix**: Wrap every `$()` call: `function safeFirst(name) { try { return $('name').first().json; } catch { return {}; } }`
- **Discovered**: 2026-03-05, Daily Brief [8] debugging
- **Times caught**: 0
- **Times missed**: 0

---

# Adding New Patterns

When a new failure is discovered during import testing:

1. Assign the next P-number (P010, P011, etc.)
2. Fill in all fields: status, severity, category, description, detection, fix, discovered
3. Set "Times caught" and "Times missed" to 0
4. Update `validate-n8n.py` if the detection logic can be automated
5. Log the discovery in `import-log.md`
