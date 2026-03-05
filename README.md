# alex-os-automations

n8n workflow definitions and automation assets for the Alex-OS operating system.

## Structure

```
alex-os-automations/
├── n8n-workflows/          ← Importable n8n workflow JSON files
│   ├── 7a-build-meeting-agendas.json
│   ├── 7b-pre-meeting-delta.json
│   ├── 8-daily-brief.json
│   ├── classify-3cv-emails.json
│   ├── index-missive-labels.json
│   └── tool-assemble-agenda.json
└── README.md
```

## Relationship to alex-os

This repo contains the **executable automation artifacts** (n8n JSON, future Relay configs).

The **context, documentation, and skills** that describe how to build and debug these automations live in [alex-os](https://github.com/alex-ahbadvisors/alex-os):
- `workflows.md` — registry of all active automations
- `skills/n8n-copilot/` — n8n building/debugging skill
- `plans/*.md` — build specs for each automation

## Usage

To import a workflow into n8n:
1. Open n8n → Workflows → Import from File
2. Select the relevant `.json` file
3. Update credentials (API keys, webhook URLs) to match your environment
