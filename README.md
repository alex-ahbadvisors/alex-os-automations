# alex-os-automations

n8n workflow definitions and automation assets for the Alex-OS operating system.

## Quick Start

```bash
# Open this repo in Claude Code
aoa

# Open both repos in one session (for work spanning agents + automations)
aosfull

# Quick save
aoasave
```

| Command | What it does |
|---------|-------------|
| `aoa` | Opens this repo in Claude Code (pulls first) |
| `aosfull` | Opens alex-os with this repo added (both repos, one session) |
| `aoasave` | Quick commit + push |

## Structure

```
alex-os-automations/
├── n8n-workflows/          <- Importable n8n workflow JSON files
│   ├── 7a-build-meeting-agendas.json
│   ├── 7b-pre-meeting-delta.json
│   ├── 8-daily-brief.json
│   ├── classify-3cv-emails.json
│   ├── index-missive-labels.json
│   └── tool-assemble-agenda.json
├── CLAUDE.md               <- Claude Code context for this repo
└── README.md
```

## Relationship to alex-os

This repo contains the **executable automation artifacts** (n8n JSON, future Relay configs).

The **context, documentation, and skills** that describe how to build and debug these automations live in [alex-os](https://github.com/alex-ahbadvisors/alex-os):
- `workflows.md` — registry of all active automations
- `skills/n8n-copilot/` — n8n building/debugging skill
- `plans/*.md` — build specs for each automation
- `tech-stack.md` — ClickUp list IDs, Missive label IDs, all integration details

## Usage

To import a workflow into n8n:
1. Open n8n → Workflows → Import from File
2. Select the relevant `.json` file
3. Update credentials (API keys, webhook URLs) to match your environment

To export a workflow from n8n back to this repo:
1. In n8n, open the workflow → three dots → Export
2. Save the `.json` to `n8n-workflows/` replacing the existing file
3. Run `aoasave` to commit and push
