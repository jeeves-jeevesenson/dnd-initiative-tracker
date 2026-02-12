# Player Character YAML Files

This directory contains YAML files that define player characters for use in the D&D Initiative Tracker application. These files serve as persistent character sheets that can be created, edited, and loaded by both the character builder GUI (`scripts/skeleton_gui.py`) and the main initiative tracker application (`dnd_initative_tracker.py`).

---

## 📋 Table of Contents

- [Overview](#overview)
- [File Format](#file-format)
- [Complete YAML Structure Reference](#complete-yaml-structure-reference)
  - [Root Level Fields](#root-level-fields)
  - [Identity Section](#identity-section)
  - [Leveling Section](#leveling-section)
  - [Abilities Section](#abilities-section)
  - [Proficiency Section](#proficiency-section)
  - [Vitals Section](#vitals-section)
  - [Defenses Section](#defenses-section)
  - [Resources Section](#resources-section)
  - [Features Section](#features-section)
  - [Actions/Reactions/Bonus Actions](#actionsreactionsbonus-actions)
  - [Spellcasting Section](#spellcasting-section)
  - [Inventory Section](#inventory-section)
  - [Notes Section](#notes-section)
- [How Character Files Are Used](#how-character-files-are-used)
  - [Character Builder GUI](#character-builder-gui-scriptskeleton_guipy)
  - [Initiative Tracker Application](#initiative-tracker-application-dnd_initative_trackerpy)
- [Creating and Editing Characters](#creating-and-editing-characters)
- [Formula System](#formula-system)
- [Best Practices](#best-practices)
- [Example Character](#example-character)

---

## Overview

Player character YAML files provide a structured, human-readable format for storing complete D&D 5e character sheets. These files are:

- **Persistent**: Character data is saved to disk and preserved between game sessions
- **Editable**: Can be edited manually in a text editor or via the GUI character builder
- **Integrated**: Automatically loaded by the initiative tracker for combat management
- **Extensible**: Support for custom features, resources, spells, and actions
- **Version Controlled**: Include a `format_version` field for future compatibility

### Key Benefits

1. **Separation of Concerns**: Player data is separate from the application logic
2. **Portability**: YAML files can be shared, backed up, and version controlled
3. **Flexibility**: Supports complex character builds with multi-classing, custom features, and homebrew content
4. **Formula Support**: Many fields accept mathematical formulas (e.g., `"10 + dex_mod"`) for dynamic calculations

---

## File Format

- **Format**: YAML (`.yaml` or `.yml` extension)
- **Location**: `players/` directory in the application root
- **Naming Convention**: Typically `Character-Name.yaml` (e.g., `Fred-Figglehorn.yaml`)
- **Encoding**: UTF-8 with support for unicode characters
- **Current Version**: `format_version: 2`

---

## Complete YAML Structure Reference

### Root Level Fields

These fields appear at the top level of the YAML file:

```yaml
format_version: 2          # Required: File format version for compatibility
name: "Character Name"     # Required: Character's name (used for display and filename generation)
player: "Player Name"      # Optional: Real-world player's name
campaign: "Campaign Name"  # Optional: Campaign identifier
ip: "192.168.1.100"       # Optional: Player's IP address for LAN features
```

**Field Descriptions:**

- **format_version**: Tracks the schema version of the YAML file. Current version is `2`. Used for future migration and backward compatibility.
- **name**: The character's in-game name. This is the primary identifier used throughout the application. Required field.
- **player**: The real-world player's name. Used for tracking who plays this character.
- **campaign**: Optional campaign name or identifier. Useful for organizing characters across multiple campaigns.
- **ip**: IP address for the player's device when using LAN/mobile client features. Can be manually set or auto-detected.

---

### Identity Section

Contains role-playing and character identity information:

```yaml
identity:
  pronouns: "He/Him"           # Character's pronouns
  ancestry: "Human"            # Race/species/ancestry
  background: "Soldier"        # Character background
  alignment: "Lawful Good"     # Alignment (e.g., Lawful Good, Chaotic Neutral)
  description: "A tall warrior with a scarred face"  # Physical description
```

**Field Descriptions:**

- **pronouns**: Character's preferred pronouns (e.g., "She/Her", "They/Them", "He/Him", custom pronouns)
- **ancestry**: Character's race or ancestry (Human, Elf, Dwarf, Tiefling, etc.). Can include subraces (e.g., "High Elf")
- **background**: Character's background (Acolyte, Criminal, Folk Hero, Noble, Sage, Soldier, etc.)
- **alignment**: Character's alignment on the Law-Chaos and Good-Evil axes
- **description**: Freeform text describing the character's appearance, mannerisms, or other notable features

---

### Leveling Section

Defines character level and class information:

```yaml
leveling:
  level: 5                  # Total character level (sum of all class levels)
  classes:                  # List of classes (supports multiclassing)
    - name: "Fighter"       # Class name
      subclass: "Champion"  # Subclass/archetype name
      level: 3              # Levels in this class
    - name: "Rogue"
      subclass: "Thief"
      level: 2
```

**Field Descriptions:**

- **level**: Total character level across all classes. Must equal the sum of individual class levels.
- **classes**: List of class objects. Supports multiclassing with multiple entries.
  - **name**: The class name (e.g., Barbarian, Bard, Cleric, Druid, Fighter, Monk, Paladin, Ranger, Rogue, Sorcerer, Warlock, Wizard)
  - **subclass**: Subclass or archetype name (e.g., Champion, Battle Master, Assassin, Arcane Trickster)
  - **level**: Number of levels in this specific class (1-20)

**Notes:**
- For single-class characters, include one class entry with `level` matching total character level
- For multiclass characters, sum of class levels must equal total `level`
- Subclass can be empty string if character hasn't chosen a subclass yet

---

### Abilities Section

The six core ability scores:

```yaml
abilities:
  str: 16    # Strength
  dex: 14    # Dexterity
  con: 15    # Constitution
  int: 10    # Intelligence
  wis: 12    # Wisdom
  cha: 8     # Charisma
```

**Field Descriptions:**

All ability scores are integers typically ranging from 3 to 20 (though values outside this range are supported for edge cases):

- **str**: Strength - Physical power, melee attacks, Athletics
- **dex**: Dexterity - Agility, AC, initiative, Acrobatics, Stealth
- **con**: Constitution - Endurance, hit points, concentration
- **int**: Intelligence - Logic, knowledge skills, wizard spellcasting
- **wis**: Wisdom - Awareness, Perception, Insight, cleric/druid spellcasting
- **cha**: Charisma - Force of personality, social skills, bard/sorcerer/warlock spellcasting

**Ability Modifiers:**
The application automatically calculates ability modifiers using the standard formula: `(score - 10) // 2`
- Example: STR 16 → +3 modifier, DEX 14 → +2 modifier, CHA 8 → -1 modifier

---

### Proficiency Section

Tracks proficiencies and expertise:

```yaml
proficiency:
  bonus: 3              # Proficiency bonus (based on level)
  saves:                # Proficient saving throws
    - dex               # Use ability abbreviations: str, dex, con, int, wis, cha
    - wis
  skills:
    proficient:         # Skills with proficiency bonus
      - athletics       # Use lowercase skill names
      - perception
      - stealth
    expertise:          # Skills with double proficiency (e.g., Rogue's Expertise)
      - stealth
      - thieves_tools
  tools:                # Tool proficiencies
    - thieves_tools
    - smiths_tools
  languages:            # Known languages
    - Common
    - Elvish
    - Thieves' Cant
```

**Field Descriptions:**

- **bonus**: Proficiency bonus, typically calculated as `2 + (level - 1) // 4`
  - Levels 1-4: +2, Levels 5-8: +3, Levels 9-12: +4, Levels 13-16: +5, Levels 17-20: +6
- **saves**: List of ability scores the character is proficient in for saving throws
  - Valid values: `str`, `dex`, `con`, `int`, `wis`, `cha`
- **skills.proficient**: List of skills the character has proficiency in (adds proficiency bonus to checks)
  - Valid skills: `acrobatics`, `animal_handling`, `arcana`, `athletics`, `deception`, `history`, `insight`, `intimidation`, `investigation`, `medicine`, `nature`, `perception`, `performance`, `persuasion`, `religion`, `sleight_of_hand`, `stealth`, `survival`
- **skills.expertise**: List of skills with expertise (adds double proficiency bonus)
  - Typically from Rogue's Expertise feature or similar class features
  - Can include tools (e.g., `thieves_tools`)
- **tools**: List of tool proficiencies
  - Examples: `thieves_tools`, `smiths_tools`, `disguise_kit`, `playing_card_set`, `lute`
- **languages**: List of known languages
  - Standard: Common, Dwarvish, Elvish, Giant, Gnomish, Goblin, Halfling, Orc
  - Exotic: Abyssal, Celestial, Draconic, Deep Speech, Infernal, Primordial, Sylvan, Undercommon
  - Secret: Druidic, Thieves' Cant

---

### Vitals Section

Health, movement, and key combat statistics:

```yaml
vitals:
  max_hp: 45                      # Maximum hit points
  current_hp: 45                  # Current hit points
  temp_hp: 0                      # Temporary hit points
  hit_dice:
    die: "d10"                    # Hit die type (d6, d8, d10, d12)
    total: 5                      # Total number of hit dice (usually equals level)
    spent: 2                      # Number of hit dice spent (refreshes on long rest)
  speed:
    walk: 30                      # Walking speed in feet
    climb: 15                     # Climbing speed (0 if none)
    fly: 0                        # Flying speed (0 if none)
    swim: 30                      # Swimming speed (0 if none)
  initiative:
    formula: "dex_mod"            # Formula for initiative calculation
  passive_perception:
    formula: "10 + wis_mod"       # Formula for passive Perception
```

**Field Descriptions:**

- **max_hp**: Maximum hit points. Calculate as: `(hit_die_average + con_mod) * level + additional_hp`
  - First level gets max hit die + CON mod
  - Subsequent levels get average (or rolled) + CON mod
- **current_hp**: Current hit points. Updated during combat.
- **temp_hp**: Temporary hit points. These are lost first before current HP.
- **hit_dice**: Hit dice for short rest healing
  - **die**: Type of hit die based on class (Wizard: d6, Rogue: d8, Fighter: d10, Barbarian: d12)
  - **total**: Total hit dice available (typically equals character level for single-class)
  - **spent**: How many hit dice have been spent (reset on long rest)
- **speed**: Movement speeds in feet per round (numeric values)
  - **walk**: Standard walking speed (typically 30 for most races, 25 for dwarves/small races)
  - **climb**: Special climbing speed (from racial traits or class features)
  - **fly**: Flying speed (from racial traits, magic items, or spells)
  - **swim**: Swimming speed (from racial traits or class features)
- **initiative.formula**: Formula for calculating initiative. Typically `"dex_mod"` but can be modified by features (e.g., Champion Fighter adds `"dex_mod + wis_mod"`)
- **passive_perception.formula**: Formula for passive Perception. Standard is `"10 + wis_mod"` plus proficiency if proficient in Perception, plus expertise bonus if applicable.

**Notes:**
- Hit dice: Multiclass characters have separate hit dice types. The `die` field can be a single type or the primary class's type.
- Formulas are evaluated by the application using character stats (see [Formula System](#formula-system))
- For `format_version: 2` files, `vitals.speed` uses the `walk/climb/fly/swim` keys with integer values representing feet.
- Legacy character files that still use `Normal/Climb/Fly/Swim` keys are normalized by the UI to the new schema on load.

---

### Defenses Section

Armor Class, resistances, immunities, and vulnerabilities:

```yaml
defenses:
  ac:
    sources:                      # List of AC sources
      - id: "unarmored"           # Unique identifier
        label: "Unarmored"        # Display name
        when: "always"            # Condition when this AC applies
        base_formula: "10 + dex_mod"  # AC calculation formula
      - id: "armor"
        label: "Chain Mail"
        when: "wearing_armor"
        base_formula: "16"
    bonuses:                      # List of AC bonuses
      - id: "shield"
        label: "+2 Shield"
        value: 2
        when: "wielding_shield"
  resistances:                    # Damage resistances
    - fire
    - cold
  immunities:                     # Damage immunities
    - poison
    - psychic
  vulnerabilities:                # Damage vulnerabilities
    - necrotic
```

**Field Descriptions:**

- **ac.sources**: List of different AC calculation methods. The highest applicable AC is used.
  - **id**: Unique identifier for this AC source
  - **label**: Human-readable name displayed in UI
  - **when**: Condition or context when this AC applies (freeform text, e.g., "always", "wearing_armor", "unarmored")
  - **base_formula**: Formula for calculating base AC (see [Formula System](#formula-system))
    - Common formulas:
      - Unarmored: `"10 + dex_mod"` or `"10 + dex_mod + con_mod"` (Barbarian) or `"13 + dex_mod"` (Monk)
      - Light Armor: `"11 + dex_mod"` (Leather), `"12 + dex_mod"` (Studded Leather)
      - Medium Armor: `"14 + min(dex_mod, 2)"` (Scale Mail), `"15 + min(dex_mod, 2)"` (Breastplate)
      - Heavy Armor: `"16"` (Chain Mail), `"18"` (Plate)
- **ac.bonuses**: Additional AC bonuses applied on top of base AC
  - **id**: Unique identifier
  - **label**: Display name (e.g., "+2 Shield", "Ring of Protection")
  - **value**: Numeric bonus to add to AC
  - **when**: Condition when bonus applies
- **resistances**: List of damage types the character resists (takes half damage)
  - Valid types: `acid`, `bludgeoning`, `cold`, `fire`, `force`, `lightning`, `necrotic`, `piercing`, `poison`, `psychic`, `radiant`, `slashing`, `thunder`
- **immunities**: List of damage types the character is immune to (takes no damage)
- **vulnerabilities**: List of damage types the character is vulnerable to (takes double damage)

---

### Resources Section

Global resource pools for tracking limited-use abilities:

```yaml
resources:
  pools:
    - id: "action_surge"          # Unique identifier
      label: "Action Surge"       # Display name
      current: 1                  # Current uses remaining
      max_formula: "1"            # Formula for maximum uses
      reset: "short_rest"         # When pool resets
    - id: "second_wind"
      label: "Second Wind"
      current: 0
      max_formula: "1"
      reset: "short_rest"
    - id: "superiority_dice"
      label: "Superiority Dice"
      current: 4
      max_formula: "4"
      reset: "short_rest"
```

**Field Descriptions:**

- **pools**: List of resource pool objects
  - **id**: Unique identifier for the pool (used for referencing in features and actions)
  - **label**: Display name shown in UI
  - **current**: Current number of uses remaining
  - **max_formula**: Formula for calculating maximum uses (can be a number or formula like `"level // 2"`)
  - **reset**: When the pool resets to maximum
    - Valid values: `"short_rest"`, `"long_rest"`, `"dawn"`, `"dusk"`, `"never"`, `"manual"`

**Use Cases:**
- Class features with limited uses (Rage, Wild Shape, Channel Divinity)
- Combat abilities (Action Surge, Superiority Dice, Bardic Inspiration)
- Spell slots (can be tracked here or in spellcasting section)
- Racial traits with limited uses (Breath Weapon, Stone's Endurance)
- Custom abilities and homebrew features

**Notes:**
- Resource pools defined here are "global" and available at character level
- Features can also define their own resource pools (see [Features Section](#features-section))
- The initiative tracker can consume and restore these pools during gameplay

---

### Features Section

The most complex section - defines character features, abilities, and their grants:

```yaml
features:
  - id: "sneak_attack"            # Unique identifier
    name: "Sneak Attack"          # Display name
    category: "class"             # Feature category
    source: "Rogue 1"             # Where feature comes from
    description: "Deal extra damage when you have advantage or an ally is nearby."
    grants:                       # What this feature provides
      pools: []                   # Resource pools granted by this feature
      spells:                     # Spells granted by this feature
        cantrips: []              # Cantrips added to spellcasting
        casts: []                 # Spell casts granted (independent of spell slots)
      actions: []                 # Actions granted
      modifiers: []               # Stat modifiers granted
      damage_riders: []           # Additional damage granted
```

Each feature can have multiple nested components. Let's examine each `grants` subsection:

#### Feature Pools

Resource pools specific to a feature:

```yaml
grants:
  pools:
    - id: "sneak_attack_dice"
      label: "Sneak Attack Dice"
      max_formula: "ceil(level / 2)"  # Scales with level
      reset: "never"
```

#### Feature Spells

Spells granted by the feature:

```yaml
grants:
  spells:
    cantrips:                     # Cantrips added to known cantrips
      - "mage-hand"
      - "prestidigitation"
    casts:                        # Spell casts (free or resource-consuming)
      - spell: "misty-step"       # Spell identifier
        action_type: "bonus_action"
        consumes:                 # Optional: Resource cost
          pool: "ki_points"
          cost: 2
      - spell: "detect-magic"
        action_type: "action"
        consumes:
          pool: "spell_slots_1"
          cost: 1
```

LAN client behavior for `consumes.pool` grants:
- Pool-granted spells appear in cast presets even if not prepared.
- Casting consumes the configured resource pool first (not spell slots).
- If the pool is exhausted, free-only grants disappear until the pool is restored.
- If a spell is both prepared and pool-granted, casts use the pool while available, then fall back to normal slots.
- The LAN sheet shows a **Resource Pools** panel with `current/max` values.

**Field Descriptions:**
- **cantrips**: List of cantrip IDs added to character's known cantrips
- **casts**: List of spell cast objects
  - **spell**: Spell identifier (matches spell YAML filename in `Spells/` directory)
  - **action_type**: Type of action to cast ("action", "bonus_action", "reaction", "minute", etc.)
  - **consumes**: Optional resource consumption
    - **pool**: ID of resource pool to consume from
    - **cost**: Number of resources to consume per cast

#### Feature Actions

Actions granted by the feature:

```yaml
grants:
  actions:
    - name: "Stunning Strike"
      type: "action"              # action, bonus_action, reaction, free
      description: "When you hit with a melee weapon attack, you can spend 1 ki point to force the target to make a Constitution saving throw (DC 14) or be stunned until the end of your next turn."
      uses:                       # Optional: Limited uses
        pool: "ki_points"
        cost: 1
    - name: "Patient Defense"
      type: "bonus_action"
      description: "Spend 1 ki point to take the Dodge action as a bonus action."
      uses:
        pool: "ki_points"
        cost: 1
```

**Field Descriptions:**
- **name**: Name of the action
- **type**: Action type
  - `"action"`: Full action
  - `"bonus_action"`: Bonus action
  - `"reaction"`: Reaction
  - `"free"`: Free action (no action cost)
- **description**: Freeform text describing what the action does
- **uses**: Optional resource consumption
  - **pool**: Resource pool ID
  - **cost**: Cost per use

#### Feature Modifiers

Stat modifiers granted by the feature:

```yaml
grants:
  modifiers:
    - target: "ac"                # What stat to modify
      mode: "add"                 # How to apply the modifier
      value: 2                    # Amount (can be formula)
      when: "unarmored"           # Condition when applies
    - target: "initiative"
      mode: "add"
      value: "wis_mod"
      when: "always"
    - target: "speed.Normal"
      mode: "add"
      value: 10
      when: "unarmored"
```

**Field Descriptions:**
- **target**: What stat to modify
  - Common targets: `"ac"`, `"initiative"`, `"speed.Normal"`, `"speed.Fly"`, `"spell_save_dc"`, `"spell_attack"`, specific skills
- **mode**: How to apply the modification
  - `"add"`: Add value to target
  - `"multiply"`: Multiply target by value
  - `"set"`: Set target to value
  - `"advantage"`: Grant advantage on rolls
  - `"disadvantage"`: Grant disadvantage on rolls
- **value**: Amount of modification (can be a number or formula)
- **when**: Condition when modifier applies (freeform text)

#### Damage Riders

Additional damage added to attacks:

```yaml
grants:
  damage_riders:
    - name: "Sneak Attack"
      when: "has_advantage_or_ally_nearby"
      dice: "3d6"                 # Dice formula
      dtype: "none"               # Damage type
    - name: "Divine Smite"
      when: "uses_spell_slot"
      dice: "2d8"
      dtype: "radiant"
    - name: "Hex"
      when: "target_hexed"
      dice: "1d6"
      dtype: "necrotic"
```

**Field Descriptions:**
- **name**: Name of the damage rider
- **when**: Condition when the extra damage applies (freeform text)
- **dice**: Dice formula for extra damage (e.g., `"1d6"`, `"2d8"`, `"3d10"`)
- **dtype**: Damage type
  - Valid types: `"acid"`, `"bludgeoning"`, `"cold"`, `"fire"`, `"force"`, `"lightning"`, `"necrotic"`, `"piercing"`, `"poison"`, `"psychic"`, `"radiant"`, `"slashing"`, `"thunder"`, `"none"`

#### Complete Feature Example

```yaml
features:
  - id: "ki"
    name: "Ki"
    category: "class"
    source: "Monk 2"
    description: "Harness the mystic energy of ki."
    grants:
      pools:
        - id: "ki_points"
          label: "Ki Points"
          max_formula: "level"    # Scales with monk level
          reset: "short_rest"
      actions:
        - name: "Flurry of Blows"
          type: "bonus_action"
          description: "Spend 1 ki point to make two unarmed strikes."
          uses:
            pool: "ki_points"
            cost: 1
        - name: "Patient Defense"
          type: "bonus_action"
          description: "Spend 1 ki point to take the Dodge action."
          uses:
            pool: "ki_points"
            cost: 1
        - name: "Step of the Wind"
          type: "bonus_action"
          description: "Spend 1 ki point to Dash or Disengage, and your jump distance is doubled."
          uses:
            pool: "ki_points"
            cost: 1
```

**Feature Categories:**

Common values for the `category` field:
- `"class"`: Class features (e.g., Rage, Sneak Attack, Divine Smite)
- `"subclass"`: Subclass features (e.g., Assassinate, Battle Master Maneuvers)
- `"racial"`: Racial traits (e.g., Darkvision, Breath Weapon)
- `"feat"`: Feats (e.g., Great Weapon Master, Sharpshooter)
- `"background"`: Background features
- `"item"`: Magic items
- `"other"`: Miscellaneous features

---

### Actions/Reactions/Bonus Actions

Direct action definitions (alternative to defining in features):

```yaml
actions:
  - name: "Attack"
    description: "Make a weapon or unarmed attack against a target within range."
    type: "action"
  - name: "Dash"
    description: "Gain extra movement for the current turn equal to your speed."
    type: "action"
  - name: "Disengage"
    description: "Your movement does not provoke opportunity attacks for the rest of the turn."
    type: "action"
  - name: "Dodge"
    description: "Until the start of your next turn, attack rolls against you have disadvantage if you can see the attacker, and you make Dexterity saves with advantage."
    type: "action"
  - name: "Help"
    description: "Aid a creature in the next ability check or attack roll against a target within 5 feet of you."
    type: "action"
  - name: "Hide"
    description: "Attempt to hide by making a Dexterity (Stealth) check."
    type: "action"
  - name: "Influence"
    description: "Attempt to influence a creature through conversation, bargaining, or intimidation."
    type: "action"
  - name: "Magic"
    description: "Cast a spell or use a magical feature that takes an action."
    type: "action"
  - name: "Ready"
    description: "Prepare an action and a trigger; use your reaction to perform it when the trigger occurs."
    type: "action"
  - name: "Search"
    description: "Devote attention to finding something by making a Wisdom (Perception) or Intelligence (Investigation) check."
    type: "action"
  - name: "Study"
    description: "Focus on detailed observation or research to gain information about a creature, object, or situation."
    type: "action"
  - name: "Utilize"
    description: "Use an object or interact with the environment in a significant way."
    type: "action"

reactions:
  - name: "Opportunity Attack"
    description: "When a hostile creature you can see moves out of your reach, you can use your reaction to make one melee attack against it."
    type: "reaction"
  - name: "Reaction"
    description: "You can take a reaction when a trigger occurs. A reaction is only available once per round."
    type: "reaction"

bonus_actions:
  - name: "Bonus Action"
    description: "You can take a bonus action only when a feature, spell, or ability says you can."
    type: "bonus_action"
```

New characters start with the full basic list above; you can add or remove entries as needed.

**Field Descriptions:**

These sections provide an alternative way to define actions without using the features system:

- **name**: Name of the action
- **description**: What the action does
- **type**: Action type (`"action"`, `"reaction"`, or `"bonus_action"`)

**Notes:**
- These are simpler than feature-granted actions (no resource tracking)
- Best for actions that are always available or don't consume resources
- For complex actions with resource management, use the features system instead

---

### Spellcasting Section

Complete spellcasting configuration:

```yaml
spellcasting:
  enabled: true                   # Whether character is a spellcaster
  spell_yaml_paths:               # Where to find spell definitions
    - "./Spells"
  casting_ability: "int"          # Spellcasting ability modifier
  save_dc_formula: "8 + prof + casting_mod"      # Spell save DC formula
  spell_attack_formula: "prof + casting_mod"     # Spell attack bonus formula
  cantrips:
    max: 4                        # Maximum cantrips known
    known:                        # List of known cantrips
      - "fire-bolt"
      - "mage-hand"
      - "prestidigitation"
      - "ray-of-frost"
  known_spells:
    max: 12                       # Maximum spells known (for spontaneous casters)
    known:                        # List of known spells
      - "detect-magic"
      - "magic-missile"
      - "shield"
      - "misty-step"
      - "scorching-ray"
  prepared_spells:
    max_formula: "int_mod + level"  # Formula for max prepared spells
    prepared:                     # List of prepared spells
      - "detect-magic"
      - "magic-missile"
      - "shield"
      - "misty-step"
```

**Field Descriptions:**

- **enabled**: Boolean - whether character can cast spells
- **spell_yaml_paths**: List of directories containing spell YAML files
  - Typically `["./Spells"]` to use the application's spell library
- **casting_ability**: Ability score used for spellcasting
  - Valid values: `"int"`, `"wis"`, `"cha"`, `"str"`, `"dex"`, `"con"`
  - Common by class:
    - Wizards: `"int"`
    - Clerics, Druids, Rangers: `"wis"`
    - Bards, Sorcerers, Warlocks, Paladins: `"cha"`
- **save_dc_formula**: Formula for spell save DC
  - Standard: `"8 + prof + casting_mod"`
  - Can be customized for homebrew or special features
- **spell_attack_formula**: Formula for spell attack rolls
  - Standard: `"prof + casting_mod"`
- **cantrips.max**: Maximum cantrips the character can know
- **cantrips.known**: List of cantrip IDs currently known
  - IDs match spell filenames in spell directories (e.g., `"fire-bolt"` → `Spells/fire-bolt.yaml`)
- **known_spells**: For spontaneous casters (Bards, Sorcerers, Warlocks)
  - **max**: Maximum spells known (increases with level)
  - **known**: List of spell IDs the character knows
- **prepared_spells**: For preparation casters (Clerics, Druids, Paladins, Wizards)
  - **max_formula**: Formula for maximum prepared spells
    - Cleric/Druid: `"wis_mod + level"`
    - Paladin: `"cha_mod + level // 2"`
    - Wizard: `"int_mod + level"`
  - **prepared**: List of spell IDs currently prepared

**Spell Slots:**
- Spell slots are typically managed by the initiative tracker based on character level and class
- The tracker calculates available spell slots using standard 5e rules
- Spell slot usage is tracked during combat and can be modified in real-time

**Notes:**
- Use `casting_mod` in formulas - it automatically references the specified casting ability modifier
- Spell IDs should match spell filenames (typically kebab-case)
- The application validates spell IDs against available spell YAML files

---

### Inventory Section

Currency and item management:

```yaml
inventory:
  currency:
    gp: 150                       # Gold pieces
    sp: 25                        # Silver pieces
    cp: 8                         # Copper pieces
  items:
    - name: "Longsword"
      quantity: 1
      description: "A well-crafted longsword."
    - name: "Healing Potion"
      quantity: 3
      description: "Restores 2d4+2 hit points."
    - name: "Rope, Hempen (50 feet)"
      quantity: 1
      description: "Standard adventuring rope."
```

**Field Descriptions:**

- **currency**: Monetary wealth
  - **gp**: Gold pieces
  - **sp**: Silver pieces
  - **cp**: Copper pieces
  - Note: Can also track `pp` (platinum pieces), `ep` (electrum pieces) if desired
- **items**: List of inventory items
  - **name**: Item name
  - **quantity**: Number of items
  - **description**: Item description or notes

**Notes:**
- The inventory system is primarily for record-keeping
- The initiative tracker does not currently use inventory items in combat mechanics
- Items with mechanical effects (magic items) should be defined as features

---

### Notes Section

Freeform notes storage:

```yaml
notes:
  backstory: "Grew up in the slums of Waterdeep, learned to survive by wit and blade."
  personality: "Quick with a joke, slow to trust, always looking for the angle."
  goals: "Find the person who betrayed my mentor and bring them to justice."
  dm_notes: "Has a mysterious patron watching from the shadows."
```

**Field Descriptions:**

The `notes` section is a flexible dictionary for storing any additional character information:
- Keys can be any string (e.g., `"backstory"`, `"personality"`, `"goals"`, `"dm_notes"`)
- Values are freeform text
- Not used by application logic - purely for player/DM reference

**Common Use Cases:**
- Character backstory and history
- Personality traits, ideals, bonds, flaws
- Character goals and motivations
- DM-specific notes and secrets
- Session recaps or important story events
- Relationships with NPCs and other PCs

---

## How Character Files Are Used

### Character Builder GUI (`scripts/skeleton_gui.py`)

The character builder is a **Tkinter-based wizard application** for creating and editing character YAML files.

#### Features:

1. **Multi-Page Wizard**: 8 pages guiding users through character creation
   - Setup: Load existing characters or create new
   - Basics: Name, player, identity information
   - Level & Abilities: Class levels and ability scores
   - Vitals: HP, hit dice, speeds, formulas
   - Resources: Global resource pool management
   - Spellcasting: Full spellcasting configuration
   - Features: Complex feature editor with pools, spells, actions, modifiers, damage riders
   - Review/Save: YAML preview and save

2. **State Persistence**: Pages remember input when navigating back/forth

3. **Auto-Discovery**: Automatically finds spell directories and existing characters

4. **YAML I/O**:
   - Load: `yaml.safe_load()` with defensive default merging
   - Save: `yaml.safe_dump()` to `players/` directory
   - Auto-generates filename from character name

5. **Validation**: Each page validates input before advancing

#### Usage:

```bash
# Run the character builder
python scripts/skeleton_gui.py

# The GUI will:
# 1. Show setup page with list of existing characters
# 2. Click "New Character" to start from scratch
# 3. Click character name to load and edit existing character
# 4. Navigate through pages using "Next" and "Back" buttons
# 5. Save from Review/Save page or "File → Save" menu
```

#### Key Methods:

- `load_character(path)`: Load YAML file into editor
- `save_current()`: Save character to `players/` directory
- `save_as()`: Save with new filename
- `new_character()`: Reset and start fresh character
- `show_page(idx)`: Navigate between wizard pages

**Best Practice**: Use the GUI for creating characters to ensure proper structure and validation. Manual editing is possible but requires understanding the complete schema.

---

### Initiative Tracker Application (`dnd_initative_tracker.py`)

The main application uses character YAML files during gameplay for combat tracking and character management.

#### How Characters Are Loaded:

1. **Auto-Discovery**: Application scans `players/` directory for all `.yaml` and `.yml` files
2. **Caching**: Implements file stat metadata caching to avoid re-parsing unchanged files
3. **Parsing**: Uses `yaml.safe_load()` to load character data
4. **Roster**: Characters are added to the available roster and can be seeded into initiative

#### Character Data Usage During Combat:

**Initiative & Combat:**
- **Auto-Seeding**: Characters can be automatically added to initiative order from roster
- **Initiative Rolls**: Uses `initiative.formula` for calculating initiative (typically `dex_mod`)
- **Turn Tracking**: Tracks current turn, round count, and turn count

**Vitals & Resources:**
- **HP Tracking**: Monitors `current_hp`, `max_hp`, and `temp_hp`
- **Resource Pools**: Tracks usage of limited resources (Action Surge, Ki Points, Spell Slots, etc.)
- **Movement**: Uses `speed.Normal`, `speed.Fly`, etc. for battle map movement tracking
- **Actions**: Tracks actions, bonus actions, and reactions per turn

**Combat Capabilities:**
- **Ability Scores**: Calculates attack rolls, saving throws, and skill checks using ability modifiers
- **AC**: Determines armor class from `defenses.ac` sources and bonuses
- **Saving Throws**: Uses proficiency data for saving throw calculations
- **Resistances/Immunities**: Applies damage resistances, immunities, and vulnerabilities

**Spellcasting:**
- **Spell Lists**: Loads known spells, prepared spells, and cantrips
- **Spell Slots**: Manages spell slot usage during combat
- **Spell Attack/Save DC**: Calculates using formulas from character data
- **Spell Modifications**: Saves spell configuration changes back to YAML file

**LAN/Mobile Client:**
- **Character Data Sync**: Sends character profiles to mobile clients via WebSocket
- **Token Colors**: Saves custom token colors back to character YAML
- **Player Control**: Players can view their character stats, spells, and actions on mobile devices

#### Persistence:

Character modifications during gameplay are saved back to YAML files:
- **Spell Configuration**: Changes to prepared spells are persisted
- **Token Customization**: Custom token colors saved to character file
- **Resource Usage**: Can optionally save resource pool states between sessions

#### Usage Flow:

```
1. Application starts → Scans players/ directory
2. Character YAML files loaded into roster
3. DM seeds characters into initiative order
4. Combat begins:
   - HP damage/healing tracked
   - Resources consumed
   - Spells cast (slots consumed)
   - Movement tracked on battle map
5. End of combat:
   - Optional: Save character state
   - Spell configurations auto-saved
```

---

## Creating and Editing Characters

### Method 1: Character Builder GUI (Recommended)

Use the character builder for a guided experience:

```bash
python scripts/skeleton_gui.py
```

**Advantages:**
- Guided wizard with validation
- Visual spell picker with search
- Feature editor with tabs for pools/spells/actions/modifiers/damage
- YAML preview before saving
- Error checking

### Method 2: Manual Editing

Edit YAML files directly in a text editor:

1. **Create New File**: Start with Fred-Figglehorn.yaml as a template
2. **Copy Structure**: Duplicate the file and rename it
3. **Edit Fields**: Modify values as needed
4. **Validate**: Ensure YAML syntax is correct (use a YAML validator)
5. **Test**: Load character in the initiative tracker to verify

**Tips for Manual Editing:**
- Use consistent indentation (2 or 4 spaces, no tabs)
- Quote strings that contain special characters or start with numbers
- Validate formulas use correct variable names (e.g., `dex_mod`, `prof`, `level`)
- Reference spell IDs correctly (match spell YAML filenames)
- Maintain proper YAML list syntax (hyphens for list items)

### Method 3: Copy and Modify Template

Use Fred-Figglehorn.yaml as a template:

```bash
cd players/
cp Fred-Figglehorn.yaml My-Character.yaml
# Edit My-Character.yaml
```

---

## Formula System

Many fields support mathematical formulas that are evaluated dynamically based on character stats.

### Available Variables:

- **Ability Modifiers**: `str_mod`, `dex_mod`, `con_mod`, `int_mod`, `wis_mod`, `cha_mod`
- **Ability Scores**: `str`, `dex`, `con`, `int`, `wis`, `cha`
- **Character Level**: `level`
- **Proficiency Bonus**: `prof`
- **Spellcasting**: `casting_mod` (references the ability specified in `spellcasting.casting_ability`)

### Formula Examples:

```yaml
# Simple ability modifier reference
initiative: "dex_mod"

# Spell save DC
save_dc_formula: "8 + prof + casting_mod"

# Passive Perception
passive_perception: "10 + wis_mod"

# Multiclass spellcaster prepared spells
max_formula: "int_mod + level // 2"

# Unarmored Defense (Barbarian)
base_formula: "10 + dex_mod + con_mod"

# Unarmored Defense (Monk)
base_formula: "10 + dex_mod + wis_mod"

# Ki Points (scales with level)
max_formula: "level"

# Sneak Attack Dice (scales every 2 levels)
max_formula: "ceil(level / 2)"

# Prepared spells (full caster)
max_formula: "casting_mod + level"

# Prepared spells (half caster like Paladin)
max_formula: "cha_mod + max(1, level // 2)"
```

### Supported Operations:

- **Arithmetic**: `+`, `-`, `*`, `/`, `//` (integer division), `%` (modulo)
- **Functions**: `min()`, `max()`, `ceil()`, `floor()`, `abs()`
- **Comparison**: Can be used in conditional formulas (advanced usage)

### Formula Evaluation:

Formulas are evaluated by the application at runtime:
1. Character stats are extracted from the YAML file
2. Ability modifiers are calculated: `(score - 10) // 2`
3. Formula string is evaluated using the character's current stats
4. Result is used for the corresponding mechanic (AC, initiative, etc.)

---

## Best Practices

### 1. Use Descriptive IDs

Use clear, unique identifiers for pools, features, and resources:

```yaml
# Good
id: "action_surge"
id: "ki_points"
id: "bardic_inspiration"

# Bad
id: "pool1"
id: "feature_a"
id: "thing"
```

### 2. Document Complex Features

Use the `description` field to explain what features do:

```yaml
- id: "portent"
  name: "Portent"
  category: "subclass"
  source: "Divination Wizard 2"
  description: "Roll 2d20 at the start of the day. You can replace any attack roll, saving throw, or ability check with one of these foretelling rolls. You can do so after the roll is made but before the outcome is determined."
```

### 3. Organize Features by Category

Group features by source for easier reading:

```yaml
features:
  # Class Features
  - id: "rage"
    category: "class"
  - id: "reckless_attack"
    category: "class"
  
  # Subclass Features
  - id: "frenzy"
    category: "subclass"
  
  # Racial Traits
  - id: "darkvision"
    category: "racial"
  
  # Feats
  - id: "great_weapon_master"
    category: "feat"
```

### 4. Keep Formulas Simple

Use simple, readable formulas:

```yaml
# Good
max_formula: "level"
max_formula: "wis_mod + level"

# Acceptable
max_formula: "ceil(level / 2)"

# Avoid overly complex
max_formula: "max(1, (level // 2) + (wis_mod if wis_mod > 0 else 0))"
```

### 5. Use Standard Spell IDs

Match spell IDs to the spell filenames in the `Spells/` directory:

```yaml
# Spell file: Spells/magic-missile.yaml
known:
  - "magic-missile"  # Correct

# Spell file: Spells/fireball.yaml
known:
  - "fireball"  # Correct
  - "fire-ball"  # Incorrect (hyphen placement)
```

### 6. Validate Before Using

Always test new characters in the application:

1. Load the character in the initiative tracker
2. Verify all calculations are correct (AC, saves, etc.)
3. Check that spells load properly
4. Test resource pools function as expected
5. Verify features appear correctly

### 7. Keep Backups

Save backup copies of character files:

```bash
# Create backups directory
mkdir -p players/backups

# Back up character before major changes
cp players/My-Character.yaml players/backups/My-Character-backup-2026-01-30.yaml
```

### 8. Version Control

If using git, commit character files:

```bash
git add players/My-Character.yaml
git commit -m "Update My Character - added new spells and level 5 features"
```

---

## Example Character

Here's a complete example character demonstrating all major sections:

```yaml
format_version: 2
name: "Aria Shadowstep"
player: "Alex"
campaign: "Curse of Strahd"
ip: "192.168.1.100"

identity:
  pronouns: "She/Her"
  ancestry: "Half-Elf"
  background: "Criminal"
  alignment: "Chaotic Neutral"
  description: "A lithe rogue with silver hair and piercing green eyes. Bears a scar across her left cheek from a job gone wrong."

leveling:
  level: 5
  classes:
    - name: "Rogue"
      subclass: "Assassin"
      level: 5

abilities:
  str: 10
  dex: 18
  con: 14
  int: 12
  wis: 13
  cha: 14

proficiency:
  bonus: 3
  saves:
    - dex
    - int
  skills:
    proficient:
      - acrobatics
      - deception
      - investigation
      - perception
      - stealth
    expertise:
      - stealth
      - thieves_tools
  tools:
    - thieves_tools
    - disguise_kit
  languages:
    - Common
    - Elvish
    - Thieves' Cant

vitals:
  max_hp: 38
  current_hp: 38
  temp_hp: 0
  hit_dice:
    die: "d8"
    total: 5
    spent: 0
  speed:
    Normal: 30 ft.
    Climb: 0 ft.
    Fly: 0 ft.
    Swim: 0 ft.
  initiative:
    formula: "dex_mod"
  passive_perception:
    formula: "10 + wis_mod + prof"

defenses:
  ac:
    sources:
      - id: "leather_armor"
        label: "Leather Armor"
        when: "always"
        base_formula: "11 + dex_mod"
    bonuses: []
  resistances: []
  immunities: []
  vulnerabilities: []

resources:
  pools:
    - id: "superiority_dice"
      label: "Superiority Dice (d6)"
      current: 0
      max_formula: "0"
      reset: "short_rest"

features:
  - id: "sneak_attack"
    name: "Sneak Attack"
    category: "class"
    source: "Rogue 1"
    description: "Once per turn, deal an extra 3d6 damage to one creature you hit with an attack if you have advantage on the attack roll. The attack must use a finesse or ranged weapon. You don't need advantage if another enemy of the target is within 5 feet of it."
    grants:
      damage_riders:
        - name: "Sneak Attack"
          when: "has_advantage_or_ally_nearby"
          dice: "3d6"
          dtype: "none"

  - id: "cunning_action"
    name: "Cunning Action"
    category: "class"
    source: "Rogue 2"
    description: "You can take a bonus action on each of your turns to take the Dash, Disengage, or Hide action."
    grants:
      actions:
        - name: "Cunning Action: Dash"
          type: "bonus_action"
          description: "Double your speed for the current turn."
        - name: "Cunning Action: Disengage"
          type: "bonus_action"
          description: "Your movement doesn't provoke opportunity attacks for the rest of the turn."
        - name: "Cunning Action: Hide"
          type: "bonus_action"
          description: "Make a Dexterity (Stealth) check to hide."

  - id: "assassinate"
    name: "Assassinate"
    category: "subclass"
    source: "Assassin 3"
    description: "You have advantage on attack rolls against any creature that hasn't taken a turn in combat yet. In addition, any hit you score against a creature that is surprised is a critical hit."
    grants:
      modifiers:
        - target: "attack"
          mode: "advantage"
          value: 0
          when: "target_hasnt_acted"

  - id: "fey_ancestry"
    name: "Fey Ancestry"
    category: "racial"
    source: "Half-Elf"
    description: "You have advantage on saving throws against being charmed, and magic can't put you to sleep."
    grants: {}

actions:
  - name: "Shortsword"
    description: "Melee Weapon Attack: +7 to hit, reach 5 ft., one target. Hit: 1d6+4 piercing damage."
    type: "action"
  - name: "Shortbow"
    description: "Ranged Weapon Attack: +7 to hit, range 80/320 ft., one target. Hit: 1d6+4 piercing damage."
    type: "action"

reactions:
  - name: "Uncanny Dodge"
    description: "When an attacker you can see hits you with an attack, you can use your reaction to halve the attack's damage against you."
    type: "reaction"

bonus_actions: []

spellcasting:
  enabled: false
  spell_yaml_paths: []
  casting_ability: "int"
  save_dc_formula: "8 + prof + casting_mod"
  spell_attack_formula: "prof + casting_mod"
  cantrips:
    max: 0
    known: []
  known_spells:
    max: 0
    known: []
  prepared_spells:
    max_formula: "0"
    prepared: []

inventory:
  currency:
    gp: 250
    sp: 15
    cp: 7
  items:
    - name: "Shortsword"
      quantity: 1
      description: "Finesse weapon, 1d6 piercing"
    - name: "Shortbow"
      quantity: 1
      description: "Ranged weapon, 1d6 piercing, 80/320 ft"
    - name: "Arrows"
      quantity: 40
      description: "Ammunition for shortbow"
    - name: "Leather Armor"
      quantity: 1
      description: "AC 11 + Dex modifier"
    - name: "Thieves' Tools"
      quantity: 1
      description: "For picking locks and disarming traps"
    - name: "Disguise Kit"
      quantity: 1
      description: "For creating disguises"
    - name: "Healing Potion"
      quantity: 2
      description: "Restores 2d4+2 hit points"

notes:
  backstory: "Aria grew up on the streets of Waterdeep, learning to survive through stealth and wit. She joined the Thieves' Guild at age 14 and quickly became one of their most skilled operatives. A failed assassination attempt left her with a scar and a desire to escape the guild's influence."
  personality: "Quick with a quip and always watching the exits. Slow to trust but fiercely loyal to those who earn it."
  ideals: "Freedom above all else. Nobody should be controlled or owned."
  bonds: "My mentor in the guild saved my life. I owe them everything."
  flaws: "I can't resist a good heist, even when it's obviously a trap."
  goals: "Earn enough to buy my freedom from the Thieves' Guild and start a new life in a distant city."
```

---

## Summary

Player character YAML files are the persistent storage format for D&D 5e characters in this initiative tracker system. They provide:

- **Complete Character Data**: All stats, abilities, spells, features, and inventory
- **Formula Support**: Dynamic calculations based on character stats
- **Extensibility**: Support for homebrew content and custom features
- **Integration**: Seamless loading by both the character builder GUI and initiative tracker
- **Human-Readable**: YAML format is easy to read and edit manually

The schema is comprehensive yet flexible, supporting everything from simple martial characters to complex multiclass spellcasters with custom features and homebrew abilities.

For best results:
1. Use the character builder GUI (`scripts/skeleton_gui.py`) for initial creation
2. Refer to this README and Fred-Figglehorn.yaml as examples
3. Test characters in the initiative tracker before gameplay
4. Keep backups of character files
5. Use version control for tracking changes over time

---

**Related Files:**
- `scripts/skeleton_gui.py` - Character builder application
- `Fred-Figglehorn.yaml` - Example character file
- `dnd_initative_tracker.py` - Main application that uses these files
- `Spells/` - Spell definitions referenced by character files
- `README.md` - Main application documentation
