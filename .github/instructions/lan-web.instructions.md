---
applyTo: "assets/web/**"
---

# LAN web client instructions (assets/web)

## Protocol stability
- Assume older DM hosts and older clients may exist; prefer additive changes.
- When changing payloads: add fields rather than rename/remove; keep defaults on the client.

## UX constraints
- Mobile-first: avoid tiny tap targets, hidden overflow, or hover-only interactions.
- Keep the client lightweight (no large framework additions unless explicitly requested).

## Debuggability
- If adding UI state, expose a simple debug view/log hook rather than silent failures.
- Avoid console spam; log only meaningful state transitions or errors.
