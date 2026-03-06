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
