---
applyTo: "**/*.py"
---

# Python (Tkinter + LAN) instructions

## Design constraints
- Tkinter must remain responsive: do not block the UI thread.
- LAN server work should stay off the UI thread; use the existing queue/message passing patterns.
- Prefer minimal diffs: fix the bug with the smallest change that preserves behavior.

## Changes involving combat state
- Treat combat state as the source of truth; ensure UI + LAN clients stay consistent.
- If you change turn logic / validation, consider both DM actions and player-originated actions.

## Error handling & logging
- On user-facing errors, fail gracefully and add actionable log messages.
- Avoid noisy logs; prefer one clear line with context (what action, what inputs, what failed).

## Backwards compatibility
- Do not rename `dnd_initative_tracker.py`.
- Do not break existing YAML schemas or saved data expectations.
- Avoid changing LAN message shapes unless you maintain compatibility (e.g., new optional fields).
