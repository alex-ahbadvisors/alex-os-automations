# alex-os-automations

This repo contains n8n workflow JSON files and automation artifacts for Alex Brownstein's operating system.

## Context

- **Owner**: Alex Brownstein (AHB Advisors / 3CV)
- **Parent system**: [alex-os](https://github.com/alex-ahbadvisors/alex-os) — the full operating system with agents, skills, client context, and documentation
- **n8n instance**: ahbadvisors.app.n8n.cloud (cloud-hosted)
- **This repo**: Executable automation artifacts only. Documentation, skills, and agent definitions live in alex-os.

## Key References (in alex-os)

When working on automations, you'll often need context from alex-os. Use `--add-dir ~/alex-os` or ask Alex to provide context.

- `workflows.md` — registry of all automations, statuses, and dependencies
- `skills/n8n-copilot/` — n8n building/debugging skill with Missive API docs, JSON debugging patterns, message formatting
- `tech-stack.md` — tool profiles, ClickUp list IDs, Missive label IDs, all integration details
- `plans/*.md` — build specs for planned automations
- `agents/chief-of-staff/soul.md` — COS agent (owns morning brief logic)

## Working with n8n JSON

- Each `.json` file is a complete n8n workflow export (importable via n8n UI)
- Naming convention: `[number]-workflow-name.json` for numbered workflows, `tool-name.json` for sub-workflows
- After editing JSON here, import into n8n Cloud to test
- After editing in n8n Cloud, export and commit back here to keep in sync

## Communication Style

Same as alex-os: pyramid principle, no filler, executive-level fluency. See alex-os/CLAUDE.md for full rules.
