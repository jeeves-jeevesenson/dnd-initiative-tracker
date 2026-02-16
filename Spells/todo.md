# Spells automation todo (level 0-5 only)

Current scope for this pass: **only spells level 0 through 5**.

## Automated in this pass
- chill-touch (full attack + damage automation, cantrip scaling)
- ray-of-frost (full attack + damage automation, cantrip scaling)
- sacred-flame (full save + damage automation, cantrip scaling)
- guiding-bolt (full ranged spell attack + damage automation, slot scaling)

## Complex spells to review
- alter-self
  - Current tags/automation need a focused pass; multiple mode options are not safe to automate in a broad sweep.
- chromatic-orb
  - Damage type choice + leap behavior make this more complex than the baseline single-target automation.
- eldritch-blast
  - Beam count scales by character level and allows split targeting; needs dedicated multi-beam handling.
