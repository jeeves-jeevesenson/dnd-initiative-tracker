---
applyTo: "scripts/**"
---

# Install / update scripts instructions

## Safety & idempotence
- Scripts must be safe to rerun.
- Prefer clear failure modes with actionable messages.

## Cross-platform requirements
- If you change Linux/macOS scripts, check quoting and shell portability.
- If you change PowerShell or .bat, keep paths robust and avoid assumptions about CWD.

## Update behavior
- Update flows should show what will change and ask for confirmation before modifying installs.
- Preserve user data (saved battles/presets/players) unless an explicit uninstall path.
