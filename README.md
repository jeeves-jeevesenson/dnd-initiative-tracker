# D&D Initiative Tracker

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![UI](https://img.shields.io/badge/ui-tkinter-informational)
![LAN](https://img.shields.io/badge/LAN-fastapi%20%2B%20websocket-ffb000)
![Version](https://img.shields.io/badge/version-v41-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

<!-- Note: Update version badge when releasing new versions -->

A comprehensive D&D 5e initiative tracker and combat management system with a desktop UI for the Dungeon Master and an optional LAN/mobile web client for players. Built with Python, Tkinter, FastAPI, and WebSockets, this tool streamlines combat encounters with initiative tracking, HP management, conditions, map mode with grid-based movement, and collaborative player interaction over local networks.

> **Note on Filename**: The main script is named `dnd_initative_tracker.py` (with a historical typo: "initative" instead of "initiative"). This filename is maintained for backward compatibility with existing installations and configurations.

## 🎯 Quick Start

```bash
# Clone the repository
git clone https://github.com/YOUR-USERNAME/dnd-initiative-tracker.git  # Replace with your fork URL
cd dnd-initiative-tracker

# Install dependencies
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run the tracker
python dnd_initative_tracker.py
```

The DM window opens automatically. To enable player mobile access, use **LAN → Start LAN Server** from the menu.

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [Installation](#-installation)
- [Usage Guide](#-usage-guide)
- [LAN/Mobile Client](#-lanmobile-client)
- [Map Mode](#-map-mode)
- [Configuration](#-configuration)
- [YAML Data Files](#-yaml-data-files)
- [Keyboard Shortcuts](#-keyboard-shortcuts)
- [Advanced Features](#-advanced-features)
- [Troubleshooting](#-troubleshooting)
- [Development](#-development)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🎲 Overview

The D&D Initiative Tracker is a feature-rich combat management tool designed for tabletop RPG sessions. It provides:

- **Desktop Application** (`tkinter`): Full-featured DM interface with initiative tracking, HP management, condition tracking, death saves, damage-over-time effects, and an interactive grid-based battle map
- **Mobile Web Client** (`FastAPI` + `WebSocket`): Real-time player interface that allows players to control their characters during their turns
- **Monster & Spell Library**: YAML-based monster and spell databases with 510+ monsters and 390+ spells included
- **Persistent Logging**: Battle narration and operations logs for session review

### What Makes This Special

1. **Hybrid Architecture**: Combines the power of a native desktop app with the convenience of mobile web clients
2. **Real-Time Sync**: WebSocket-based communication keeps all players updated instantly
3. **Data-Driven**: Extensive YAML-based monster and spell libraries that are human-readable and easily extensible
4. **Battle Map**: Interactive grid-based map with token movement, AoE visualization, terrain painting, and obstacle placement
5. **Player Autonomy**: Players control their own movement and actions on their turns while the DM maintains oversight
6. **Comprehensive Conditions**: Full 2024 D&D Basic Rules condition support with automatic turn tracking and immobilization handling

### Project Structure

- **`dnd_initative_tracker.py`** (11,397 lines): Main application entry point that layers the LAN/mobile client functionality on top of the Tk desktop app
- **`helper_script.py`** (8,227 lines): Core initiative tracker implementation with Tkinter UI, battle map, and combat mechanics
- **`Monsters/`**: YAML database of 510+ monster stat blocks (2024 D&D 5e)
- **`Spells/`**: YAML database of 390+ spell definitions with mechanics
- **`players/`**: Optional YAML files for player character defaults
- **`presets/`**: Saved terrain and obstacle configurations
- **`assets/`**: Application icons, sounds (alert.wav, ko.wav), and web manifest
- **`scripts/`**: Installation and utility scripts for Linux
- **`logs/`**: Battle narration (`battle.log`) and operations (`operations.log`) logs

---

## ✨ Key Features

### Initiative & Combat Management (DM Side)

- **Initiative Tracking**: Add combatants, sort by initiative, and step through turns with hotkeys
- **Turn Management**: Track current creature, round count, and turn count with automatic cycling
- **HP Management**: 
  - Quick damage calculator with auto-remove when HP drops to 0
  - Healing tool with optional attacker logging
  - Visual HP indicators and alerts
- **Conditions**: Full 2024 D&D Basic Rules condition support
  - Blinded, Charmed, Deafened, Exhaustion, Frightened, Grappled, Incapacitated
  - Invisible, Paralyzed, Petrified, Poisoned, Prone, Restrained, Stunned, Unconscious
  - Star Advantage (expires at start of turn)
  - Stackable duration tracking with auto-countdown
  - Auto-skip turns for incapacitated/paralyzed/petrified/stunned/unconscious creatures
  - "Stand Up" button for Prone (spends half movement)
- **Damage Over Time (DOT)**: Automatic damage application at start of creature's turn
  - Burn 🔥, Poison ☠️, Necrotic 💀
  - Configurable dice rolls per DOT type
- **Death Saves**: Track death save successes/failures with automatic stabilization and death
- **Ally/Enemy Indicators**: Color-coded names (green for allies, red for enemies)
- **Monster Library**: Dropdown selection from 510+ pre-loaded monster YAML files
- **Persistent History**: All combat events logged to file with timestamps

### Map Mode (DM Side)

- **Grid-Based Map**: Configurable grid size with drag-and-drop token placement
- **Token Movement**: 
  - Drag creatures to move them on the map
  - Movement validation based on creature speed
  - Visual movement range indicators
  - Automatic movement deduction on player turns
- **Terrain Painting**: Paint rough terrain and water tiles
  - Multiple terrain presets (Mud, Water, Grass, Stone, Sand, Magic, Shadow)
  - Rough terrain costs double movement
  - Water terrain requires swim speed
- **Obstacles**: Place, move, and save obstacle configurations
  - Circle, square, and custom-shaped obstacles
  - Save/load obstacle presets for reusable map layouts
- **Area of Effect (AoE) Visualization**:
  - Place **circle**, **square**, or **line** AoE overlays
  - Custom names, colors, and transparency
  - Optional save DC and damage metadata
  - Export AoE data for documentation
- **Background Images**: Load custom map backgrounds (requires Pillow)
- **Grid Customization**: Adjustable cell size and map dimensions

### LAN / Mobile Client (Player Side)

- **Real-Time WebSocket Communication**: Instant updates for all connected players
- **Auto-Assignment**: Players are automatically assigned to their character by IP address
- **Turn-Based Control**: Players can only act during their own turn
- **Mobile-Optimized UI**: 
  - Progressive Web App (PWA) support with offline capability
  - Responsive design for phones and tablets
  - Touch-optimized controls
- **Action Tracking**: Move, action, and bonus action counters with visual feedback
- **Token Movement**: Players move their own tokens on the map during their turn
- **Spell Management**: 
  - Browse and cast spells from the spell library
  - Filter by spell level
  - View spell details and mechanics
- **Turn Notifications**: 
  - Visual and audio alerts when it's your turn
  - iOS/iPadOS Web Push support (requires Add to Home Screen on iOS 16.4+)
  - Vibration/haptic feedback
- **Session Management**: DM can view and disconnect connected clients

### Technical Features

- **FastAPI Web Server**: High-performance async web server for LAN clients
- **WebSocket Protocol**: Real-time bidirectional communication
- **YAML Configuration**: Human-readable data files for monsters, spells, and players
- **Logging System**: Comprehensive logging to both file and console
- **QR Code Generation**: Easy connection for mobile devices
- **Admin Authentication**: Optional password protection for DM controls
- **Host-Based Assignment**: Persistent player-to-character mapping by IP address

---

## 🏗️ Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     DM Desktop Application                   │
│                    (Tkinter + Python)                        │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │  Initiative    │  │   Map Mode     │  │   Logging    │  │
│  │   Tracker      │  │   (Canvas)     │  │   System     │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ Control API
                           │
┌──────────────────────────▼──────────────────────────────────┐
│               LAN Server (FastAPI + WebSocket)              │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │  REST API      │  │  WebSocket     │  │  Push Notify │  │
│  │  Endpoints     │  │  Manager       │  │  Service     │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ WebSocket
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              Mobile Web Clients (HTML/JS/CSS)               │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │  Player 1      │  │  Player 2      │  │  Player N    │  │
│  │  (iPhone)      │  │  (Android)     │  │  (Tablet)    │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **DM Actions** → Update local Tkinter state
2. **State Changes** → Broadcast to all connected WebSocket clients
3. **Player Actions** → Sent via WebSocket to server
4. **Server Validation** → Check turn ownership and movement legality
5. **Update Propagation** → Broadcast updates to DM app and all clients
6. **Logging** → Write combat events to persistent log files

### Threading Model

- **Main Thread**: Tkinter event loop (DM UI)
- **Background Thread**: FastAPI/Uvicorn server (LAN/WebSocket)
- **Thread-Safe Communication**: Queue-based message passing between threads

---

## 💻 Installation

### Prerequisites

- **Python 3.9 or higher**
- **Tkinter** (often bundled with Python; on Linux may require `python3-tk`)
- **pip** for installing Python dependencies

### Quick Install (All Platforms)

```bash
# Clone the repository
git clone https://github.com/YOUR-USERNAME/dnd-initiative-tracker.git  # Replace with actual repo URL
cd dnd-initiative-tracker

# Create virtual environment (recommended)
python3 -m venv .venv

# Activate virtual environment
# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Dependencies

The `requirements.txt` includes:

- **fastapi**: Modern web framework for building APIs
- **uvicorn[standard]**: ASGI server for running FastAPI
- **pyyaml**: YAML parser for monster/spell data
- **pillow**: Image processing for map backgrounds and QR codes
- **qrcode**: QR code generation for easy mobile connection

### Linux Installation (Desktop Integration)

For Linux users who want desktop menu integration:

```bash
# Install system dependencies (Debian/Ubuntu)
sudo apt update
sudo apt install -y python3 python3-venv python3-tk python3-pip

# Optional: For image support
sudo apt install -y python3-pil.imagetk

# Run the installer script
./scripts/install-linux.sh

# Or install with automatic dependency installation
INSTALL_PIP_DEPS=1 ./scripts/install-linux.sh
```

This will:
- Copy the app to `~/.local/share/dnd-initiative-tracker/`
- Install launcher icons (192x192 and 512x512)
- Register a desktop menu entry (`.desktop` file)
- Optionally create and populate a virtual environment

#### Linux Uninstall

```bash
./scripts/uninstall-linux.sh
```

### Supported Platforms

- **Linux**: Debian/Ubuntu-based distros with freedesktop-compliant desktop environments
- **macOS**: Should work with system Python or Homebrew Python (untested in v41)
- **Windows**: Requires Python 3.9+ with tkinter (typically included)

### Platform-Specific Notes

#### Linux
- Tkinter may need to be installed separately: `sudo apt install python3-tk`
- PIL ImageTk support: `sudo apt install python3-pil.imagetk`
- Case-sensitive filesystem: Ensure `Monsters/` and `Spells/` folders are capitalized

#### macOS
- Python from python.org includes tkinter
- Homebrew Python may require: `brew install python-tk`

#### Windows
- Python from python.org includes tkinter by default
- Use `py` launcher if multiple Python versions installed: `py -3.9 -m venv .venv`

---

## 📖 Usage Guide

### Starting the Application

```bash
# From the project directory
python dnd_initative_tracker.py
```

Or if you installed on Linux with the installer script:
- Launch from your desktop application menu (Games → D&D Initiative Tracker)
- Or run: `~/.local/share/dnd-initiative-tracker/launch-inittracker.sh`

### Basic DM Workflow

1. **Add Combatants**:
   - Click "Add Combatant" or press a hotkey
   - Select from monster dropdown or enter custom name
   - Set initiative, HP, and movement speed
   - Mark as ally or enemy

2. **Start Combat**:
   - Click "Sort Initiative" to order combatants
   - Click "Start/Resume" or press `Space` to begin
   - Current turn is highlighted

3. **Manage Turns**:
   - Press `Space` to advance to next turn
   - Press `Shift+Space` to go back to previous turn
   - Press `d` for damage tool
   - Press `h` for healing tool
   - Press `c` for condition management
   - Press `t` for death saves/DOT

4. **Track HP**:
   - Use damage tool (`d`) to apply damage with calculations
   - Use healing tool (`h`) to restore HP
   - Creatures automatically removed at 0 HP (configurable)

5. **Apply Conditions**:
   - Press `c` to open conditions dialog
   - Select condition(s) from the 2024 Basic Rules list
   - Set duration in rounds
   - Conditions auto-decrement at end of each turn

6. **Open Map Mode**:
   - Press `p` or use menu to open battle map
   - Drag tokens to move creatures
   - Paint terrain and place obstacles
   - Add AoE overlays for spells

### Using the Battle Map

See the [Map Mode](#-map-mode) section below for detailed map usage.

### Enabling LAN/Mobile Play

See the [LAN/Mobile Client](#-lanmobile-client) section below.

---

## 📱 LAN/Mobile Client

The LAN server allows players to connect from their phones, tablets, or laptops to control their characters during combat.

### Quick Setup

1. **Start the Server**:
   - In the DM app, go to **LAN → Start LAN Server**
   - Server starts on `http://0.0.0.0:8787` by default

2. **Share Connection Info**:
   - **LAN → Show LAN URL**: Displays the connection URL
   - **LAN → Show QR Code**: Shows a QR code for easy scanning
   - Example URL: `http://192.168.1.100:8787`

3. **Players Connect**:
   - Players open the URL in their mobile browser
   - They are automatically assigned to their character (by IP)
   - On iOS: "Add to Home Screen" for PWA experience and Web Push

4. **Monitor Sessions**:
   - **LAN → Sessions...**: View all connected clients
   - See who claimed which character
   - Disconnect players if needed

### Auto-Start Configuration

Edit `dnd_initative_tracker.py` to enable auto-start:

```python
# Near the top of the file
POC_AUTO_START_LAN = True  # Starts LAN server at launch
POC_AUTO_SEED_PCS = True   # Auto-adds PCs from players/ folder
```

### Mobile Client Features

When a player connects:

1. **Automatic Assignment**: 
   - Server assigns the player to their character based on IP address
   - Mapping is saved in `players/.host-assignments.yaml`
   - Players can only control their assigned character

2. **Turn Indicators**:
   - Large banner shows whose turn it currently is
   - Visual and audio alerts when it's your turn
   - Web Push notifications (iOS 16.4+, Android, desktop browsers)

3. **Movement Controls**:
   - During your turn, drag your token on the map
   - Movement deducted from available speed
   - Move/Action/Bonus Action counters track actions taken

4. **Spell Casting** (if configured):
   - Browse spell library filtered to your known spells
   - View spell details and mechanics
   - Cast spells with targeting information

5. **Character Status**:
   - View current HP, conditions, and speed
   - See active conditions with durations
   - Monitor death saves if downed

### Network Configuration

Default settings (in `dnd_initative_tracker.py`):

```python
@dataclass
class LanConfig:
    bind_host: str = "0.0.0.0"  # Listen on all interfaces
    bind_port: int = 8787       # Default port
    # ... other settings
```

**Firewall Note**: Ensure port 8787 (or your chosen port) is open on the DM's machine.

### iOS/iPadOS Web Push

iOS Web Push requires:
- iOS/iPadOS 16.4 or later
- Web app saved to Home Screen ("Add to Home Screen")
- Push notifications enabled in iOS Settings

Note: Haptics and vibration are OS-controlled and cannot be customized by the app.

### Security Considerations

The LAN server is designed for **trusted local networks** (home Wi-Fi, private LAN). It is **not hardened for internet exposure**. 

- Keep it on your local network only
- For remote play, use a VPN or add authentication
- Admin password can be configured for DM-only actions

---

## 🗺️ Map Mode

Map Mode provides a grid-based battle map with drag-and-drop token movement, terrain painting, and AoE visualization.

### Opening Map Mode

- Press `p` keyboard shortcut
- Or from menu: **Combat → Open Map** (or similar)

### Map Features

#### Token Movement

1. **Drag Tokens**: Click and drag creature tokens to move them
2. **Movement Validation**: 
   - Movement cost calculated based on terrain
   - Rough terrain costs 2× movement
   - Water requires swim speed
   - Red highlight if movement exceeds available speed
3. **Turn-Based Movement**: 
   - Movement automatically deducted on player turns
   - Movement resets at start of next turn

#### Terrain Painting

1. **Select Terrain Type**: 
   - Click terrain preset button (Mud, Water, Grass, etc.)
   - Or create custom terrain with color picker

2. **Paint Mode**:
   - Click cells to paint individual cells
   - Click and drag to paint multiple cells

3. **Terrain Effects**:
   - **Rough Terrain** (🌿): Costs 2× movement
   - **Water** (💧): Requires swim speed
   - Visual indicators show terrain type

4. **Terrain Presets**:
   - Mud: Brown, rough terrain
   - Water: Blue, swim only
   - Grass: Green, rough terrain
   - Stone: Gray, rough terrain
   - Sand: Tan, rough terrain
   - Magic: Purple, rough terrain
   - Shadow: Dark gray, rough terrain

#### Obstacles

1. **Place Obstacles**:
   - Select obstacle tool
   - Click to place circle or square obstacle
   - Drag to resize

2. **Move Obstacles**: Drag existing obstacles to reposition

3. **Save/Load Presets**:
   - Save current obstacle layout for reuse
   - Load saved presets for recurring maps
   - Presets stored in `presets/` directory

#### Area of Effect (AoE)

1. **Add AoE Overlay**:
   - Click "Add AoE" button
   - Choose shape: Circle, Square, or Line
   - Set size (radius/width)

2. **Configure AoE**:
   - **Name**: Label for the effect (e.g., "Fireball")
   - **Color**: Visual color with transparency
   - **Save DC**: Optional save difficulty class
   - **Damage**: Optional damage dice (e.g., "8d6")
   - **Damage Type**: Fire, Cold, Lightning, etc.

3. **Manage AoEs**:
   - Drag to reposition
   - Right-click to edit or remove
   - Export AoE data for documentation

4. **Color Presets**:
   - Blue (spells like Ice Storm)
   - Green (poison clouds)
   - Purple (magical effects)
   - Red (fire effects)
   - Orange (explosions)
   - Yellow (lightning)
   - Gray (fog/smoke)
   - Black (darkness)

#### Background Images

1. **Load Background**:
   - Menu option to load image (requires Pillow)
   - Image scaled to fit map dimensions
   - Grid overlaid on top of image

2. **Supported Formats**: PNG, JPEG, GIF, BMP

### Map Configuration

- **Grid Size**: Adjustable cell size (default 5 feet per square)
- **Map Dimensions**: Configure map width and height
- **Zoom**: Zoom in/out for detail or overview (if supported)

---

## ⚙️ Configuration

### Application Settings

Configuration can be adjusted by editing `dnd_initative_tracker.py`:

```python
# Near the top of the file

# Auto-start LAN server on launch
POC_AUTO_START_LAN = True  # Set to False to disable

# Auto-seed PCs from players/ folder
POC_AUTO_SEED_PCS = True  # Set to False to disable

# LAN server configuration
@dataclass
class LanConfig:
    bind_host: str = "0.0.0.0"      # Listen address
    bind_port: int = 8787            # Port number
    admin_password: str = ""         # Optional admin password
    # ... more settings
```

### Default Starting Players

Edit `helper_script.py` to change default PC names:

```python
DEFAULT_STARTING_PLAYERS = [
    "John Twilight",
    "стихия",
    "Thibble Wobblepop",
    # Add your player names here
]
```

Or create `players/*.yaml` files (see YAML section).

### Terrain Presets

Customize terrain types in `helper_script.py`:

```python
DEFAULT_ROUGH_TERRAIN_PRESETS = [
    {"label": "Mud", "color": "#8d6e63", "is_swim": False, "is_rough": True},
    {"label": "Water", "color": "#4aa3df", "is_swim": True, "is_rough": False},
    # Add custom terrain types here
]
```

### Damage Types

Add or modify damage types in `helper_script.py`:

```python
DAMAGE_TYPES = [
    "",
    "Acid",
    "Bludgeoning",
    "Cold",
    # Add custom damage types
]
```

---

## 📁 YAML Data Files

The tracker uses YAML files for extensible data storage. This allows easy addition of monsters, spells, and player defaults without modifying code.

### Monster YAML Files

Location: `Monsters/*.yaml` or `Monsters/*.yml`

**Important**: On Linux, ensure the folder is named `Monsters/` (capital M) due to case sensitivity.

#### Schema

Monsters use a stat-block-oriented schema optimized for quick reference:

```yaml
monster:
  name: Goblin
  type: humanoid
  size: Small
  alignment: Neutral Evil
  challenge:
    cr: 0.25
    xp: 50
  defenses:
    ac: 15
    hit_points:
      average: 7
      formula: 2d6
  speed:
    walk_ft: 30
    swim_ft: 0
  abilities:
    str: 8
    dex: 14
    con: 10
    int: 10
    wis: 8
    cha: 8
  initiative:
    modifier: 2
  saving_throws:
    dex: +4
  skills:
    - Stealth +6
  senses: "Darkvision 60 ft."
  languages:
    - Common
    - Goblin
  traits:
    - name: Nimble Escape
      desc: "The goblin can take the Disengage or Hide action as a bonus action on each of its turns."
  actions:
    - name: Scimitar
      desc: "Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 5 (1d6 + 2) slashing damage."
```

#### Key Fields

- **name**: Display name for the creature
- **challenge.cr**: Challenge rating (used for XP)
- **defenses.hit_points.average**: Starting HP
- **speed.walk_ft**: Base walking speed
- **speed.swim_ft**: Swimming speed (0 if none)
- **abilities**: STR, DEX, CON, INT, WIS, CHA scores
- **initiative.modifier**: Initiative bonus

The tracker currently includes **510+ monster files** covering common D&D 5e creatures.

For detailed schema documentation, see: [`Monsters/README.md`](Monsters/README.md)

### Spell YAML Files

Location: `Spells/*.yaml` or `Spells/*.yml`

**Important**: On Linux, ensure the folder is named `Spells/` (capital S).

#### Schema

Spells use a more complex schema with both display fields and mechanical data:

```yaml
schema: dnd55.spell.v1
id: fireball
name: Fireball
edition: "2024"
level: 3
school: evocation
casting_time: "Action"
range: "150 feet"
components: "V, S, M (bat guano and sulfur)"
duration: "Instantaneous"
ritual: false
concentration: false
lists:
  classes: [sorcerer, wizard]
  subclasses: []
mechanics:
  automation: manual  # full | partial | manual
  targeting:
    origin: point_within_range
    range:
      kind: distance
      distance_ft: 150
    area:
      shape: sphere
      radius_ft: 20
  sequence:
    - id: explosion
      check:
        kind: saving_throw
        ability: dex
        dc: spell_save_dc
      outcomes:
        fail:
          - effect: damage
            damage_type: fire
            dice: "8d6"
        success:
          - effect: damage
            damage_type: fire
            dice: "8d6"
            multiplier: 0.5
```

#### Key Fields

- **schema**: Should be `dnd55.spell.v1`
- **id**: Unique identifier (slug format)
- **level**: Spell level (0 = cantrip)
- **mechanics.automation**: 
  - `full`: Fully automated in app
  - `partial`: Partially automated
  - `manual`: Reference only
- **mechanics.targeting**: Range, area, and target selection
- **mechanics.sequence**: Spell resolution steps with effects

The tracker currently includes **390+ spell files** with varying levels of mechanical automation.

For detailed schema documentation and spell generation tools, see: [`Spells/README.md`](Spells/README.md)

### Player YAML Files

Location: `players/<Name>.yaml`

Player files provide per-character defaults and configurations.

#### Basic Schema

```yaml
name: Alice
base_movement: 30
swim_speed: 15
hp: 27
known_cantrips: 3
known_spells: 15
known_spell_names:
  - Fire Bolt
  - Mage Armor
  - Magic Missile
```

#### Extended Schema

For more detailed character sheets:

```yaml
name: Fred Figglehorn
format_version: 2
player: Fred Figglehorn
campaign: ''
ip: 192.168.1.51
identity:
  pronouns: They/Them
  ancestry: Drow
  alignment: Chaotic Evil
leveling:
  level: 5
  classes:
    - name: Warlock
      subclass: Pact of Blood
      level: 5
abilities:
  str: 6
  dex: 14
  con: 15
  int: 9
  wis: 12
  cha: 10
vitals:
  max_hp: 38
  current_hp: 10
  speed:
    walk: 30
    climb: 0
    fly: 0
    swim: 0
spellcasting:
  enabled: true
  casting_ability: cha
  cantrips:
    max: 4
    known: []
  known_spells:
    max: 12
    known:
      - detect-thoughts
      - dissonant-whispers
      - hellish-rebuke
  prepared_spells:
    max_formula: '6'
    prepared:
      - armor-of-agathys
      - hellish-rebuke
```

#### Key Fields

- **name** or **player**: Character name
- **base_movement** or **vitals.speed.walk**: Walking speed in feet
- **swim_speed** or **vitals.speed.swim**: Swimming speed
- **hp** or **vitals.max_hp**: Maximum HP
- **known_spell_names** or **spellcasting.known_spells.known**: List of spell IDs
- **ip**: For host-based assignment in LAN mode

### Auto-Seeding Players

If `POC_AUTO_SEED_PCS = True` in `dnd_initative_tracker.py`:

1. Scans `players/` directory for `*.yaml` files
2. Loads each player character on startup
3. Optionally rolls initiative for each PC
4. Adds them to the tracker

---

## ⌨️ Keyboard Shortcuts

The DM application has extensive keyboard shortcuts for rapid combat management:

| Key | Action |
|-----|--------|
| `Space` | Advance to next turn |
| `Shift` + `Space` | Go back to previous turn |
| `d` | Open damage tool |
| `h` | Open healing tool |
| `c` | Open conditions dialog |
| `t` | Open death saves / DOT tool |
| `m` | Open movement tool |
| `w` | Toggle water terrain for selected creature |
| `p` | Open/focus battle map |

### Damage Tool (Hotkey: `d`)

Calculator-style interface for applying damage:
- Enter damage amounts with `+` and `-` operators
- Select damage type from dropdown
- Automatically removes creature at 0 HP (configurable)
- Logs damage to battle log

### Heal Tool (Hotkey: `h`)

Simple HP restoration:
- Enter heal amount
- Optionally log attacker/source
- Cannot exceed maximum HP

### Conditions Tool (Hotkey: `c`)

Manage active conditions:
- Select one or more conditions from 2024 Basic Rules
- Set duration in rounds
- Multiple instances of same condition don't stack (except Exhaustion)
- Auto-countdown at end of each turn
- Special handling for:
  - **Prone**: "Stand Up" button (costs half movement)
  - **Star Advantage**: Auto-expires at start of turn
  - **Skip Turn**: Incapacitated, Paralyzed, Petrified, Stunned, Unconscious

### Death Saves / DOT Tool (Hotkey: `t`)

Track death saves and damage-over-time:
- **Death Saves**: Mark successes/failures
  - 3 successes = stabilized
  - 3 failures = dead
- **DOT**: Configure Burn/Poison/Necrotic effects
  - Rolls damage dice at start of creature's turn
  - Automatically applied to HP

---

## 🔧 Advanced Features

### Battle Logging

All combat events are logged to `logs/battle.log`:

```
[2026-01-30 08:15:32] Combat started: Round 1
[2026-01-30 08:15:45] Goblin 1 takes 12 fire damage (from Fireball)
[2026-01-30 08:15:47] Goblin 1 HP: 7 → 0 (removed from combat)
[2026-01-30 08:16:02] Alice healed for 8 HP
[2026-01-30 08:16:15] Round 2 begins
```

Operations logs (LAN server, WebSocket connections) go to `logs/operations.log`.

### Host-Based Player Assignment

The LAN server maintains a mapping of IP addresses to characters in `players/.host-assignments.yaml`:

```yaml
'192.168.1.51': 1  # Player ID 1
'192.168.1.52': 2  # Player ID 2
```

This allows players to reconnect and automatically reclaim their character.

### Web Push Notifications

Players receive push notifications when it's their turn:

1. **Setup** (iOS):
   - Open the URL in Safari
   - Tap Share → Add to Home Screen
   - Open the PWA from Home Screen
   - Grant notification permissions

2. **Setup** (Android/Desktop):
   - Open the URL in Chrome/Firefox/Edge
   - Grant notification permissions when prompted

3. **Notification Triggers**:
   - When it becomes the player's turn
   - When combat starts/ends
   - Custom DM announcements (if implemented)

### Admin Controls

The LAN server includes admin-only endpoints:

- **Session Management**: View all connected players
- **Force Disconnect**: Kick players from the session
- **IP Assignment**: Manually assign players to characters
- **Server Control**: Start/stop/restart the LAN server

Admin password can be set in `LanConfig.admin_password`.

### Custom Monster/Spell Generators

The repository includes tools for generating YAML files from various sources:

- **Monster Generator**: Convert stat blocks to YAML format
- **Spell Generator**: Parse spell text and extract mechanics
- **Validation Scripts**: Check YAML files for errors

See `Monsters/README.md` and `Spells/README.md` for details.

---

## 🐛 Troubleshooting

### Common Issues

#### "Module 'fastapi' not found"

**Solution**: Install LAN server dependencies:
```bash
pip install fastapi uvicorn[standard]
```

#### "Module 'qrcode' not found"

**Solution**: Install QR code generator:
```bash
pip install qrcode pillow
```

#### "PIL.ImageTk not found" (Linux)

**Solution**: Install system package:
```bash
sudo apt install python3-pil.imagetk
```

#### "Tkinter not found"

**Solution**: Install Tkinter:
```bash
# Debian/Ubuntu
sudo apt install python3-tk

# Fedora
sudo dnf install python3-tkinter

# macOS (Homebrew)
brew install python-tk
```

#### "Players can't connect to LAN server"

**Checklist**:
1. Ensure all devices are on the same network (Wi-Fi/LAN)
2. Check firewall settings (allow port 8787)
3. Verify the LAN URL shows the correct local IP
4. Test from DM's machine first: `http://localhost:8787`
5. Check logs: `logs/operations.log` for connection attempts

#### "Monsters/Spells not loading"

**Checklist**:
1. Ensure folders are named exactly `Monsters/` and `Spells/` (capitalized)
2. Check YAML syntax for errors
3. Ensure files end in `.yaml` or `.yml`
4. Check logs for parsing errors

#### "Map not showing background image"

**Solution**: Ensure Pillow is installed:
```bash
pip install pillow
```

#### "Initiative tracker window too small/large"

**Solution**: Window size is auto-adjusted based on content. To force a size, edit `helper_script.py`:
```python
# In InitiativeTracker.__init__
self.geometry("800x600")  # Width x Height
```

### Debug Mode

To enable verbose logging, edit `dnd_initative_tracker.py`:

```python
# Change logging level
logging.basicConfig(level=logging.DEBUG)
```

### Performance Issues

If the application is slow:

1. **Reduce monster/spell libraries**: Move unused files to a backup folder
2. **Disable auto-seed**: Set `POC_AUTO_SEED_PCS = False`
3. **Limit map size**: Use smaller grid dimensions
4. **Close unused windows**: Keep only necessary dialogs open

### Reporting Bugs

When reporting issues, please include:

1. Python version: `python --version`
2. Operating system and version
3. Error messages from terminal or logs
4. Steps to reproduce the issue
5. Screenshots (if applicable)

---

## 👨‍💻 Development

### Project Structure

```
dnd-initiative-tracker/
├── dnd_initative_tracker.py   # Main entry point (11,397 lines)
├── helper_script.py            # Core tracker logic (8,227 lines)
├── requirements.txt            # Python dependencies
├── .gitignore                  # Git ignore rules
├── README.md                   # This file
│
├── assets/                     # Static assets
│   ├── graphic-512.png         # App icon (512x512)
│   ├── graphic-192.png         # App icon (192x192)
│   ├── alert.wav               # Turn alert sound
│   ├── ko.wav                  # Knockout sound
│   └── manifest.webmanifest    # PWA manifest
│
├── scripts/                    # Utility scripts
│   ├── install-linux.sh        # Linux installer
│   ├── uninstall-linux.sh      # Linux uninstaller
│   └── skeleton_gui.py         # GUI development tool
│
├── Monsters/                   # Monster YAML library (510+ files)
│   ├── README.md               # Monster schema documentation
│   └── *.yaml                  # Individual monster files
│
├── Spells/                     # Spell YAML library (390+ files)
│   ├── README.md               # Spell schema documentation
│   └── *.yaml                  # Individual spell files
│
├── players/                    # Player character configs
│   ├── .host-assignments.yaml  # IP-to-player mapping
│   └── *.yaml                  # Player character files
│
├── presets/                    # Saved map configurations
│   ├── rough_terrain/          # Terrain presets
│   └── *.yaml                  # Obstacle presets
│
└── logs/                       # Application logs
    ├── battle.log              # Combat narration
    ├── operations.log          # Server operations
    └── launcher.log            # Launcher output (Linux)
```

### Key Classes

#### `dnd_initative_tracker.py`

- **`InitiativeTracker`**: Main application class (extends `base.InitiativeTracker`)
- **`LanController`**: Manages FastAPI server and WebSocket connections
- **`MonsterSpec`**: Data class for monster stat blocks
- **`PlayerProfile`**: Data class for player character profiles
- **`LanConfig`**: Configuration for LAN server

#### `helper_script.py`

- **`InitiativeTracker`**: Core Tkinter application (base class)
- **`Combatant`**: Represents a creature in combat
- **`ConditionStack`**: Manages condition durations
- **`BattleMapWindow`**: Grid-based map interface
- **`TerrainPreset`**: Terrain type configuration

### Extending the Application

#### Adding New Conditions

Edit `helper_script.py`:

```python
CONDITIONS_META: Dict[str, Dict[str, object]] = {
    # ... existing conditions
    "custom_condition": {
        "label": "Custom Condition",
        "icon": "🔮",
        "skip": False,        # Auto-skip turn?
        "immobile": False,    # Prevents movement?
    },
}
```

#### Adding New Terrain Types

Edit `helper_script.py`:

```python
DEFAULT_ROUGH_TERRAIN_PRESETS = [
    # ... existing presets
    {"label": "Lava", "color": "#ff4500", "is_swim": False, "is_rough": True},
]
```

#### Adding Custom Damage Types

Edit `helper_script.py`:

```python
DAMAGE_TYPES = [
    # ... existing types
    "Radiant",
    "Necrotic",
    "Psychic",
]
```

### Running Tests

Currently, the project does not have a formal test suite. Manual testing is recommended:

1. Start the application
2. Add several combatants
3. Test initiative sorting
4. Test combat flow (damage, healing, conditions)
5. Open map mode and test movement
6. Start LAN server and connect from mobile device
7. Test player turn interactions

### Code Style

The project follows PEP 8 with some variations:
- Line length: Generally 120 characters
- Type hints: Used throughout for clarity
- Docstrings: Provided for major functions and classes

### Contributing Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Test thoroughly
5. Commit with clear messages: `git commit -m "Add feature: ..."`
6. Push to your fork: `git push origin feature/my-feature`
7. Open a pull request

---

## 🤝 Contributing

Contributions are welcome! Here are some ways you can help:

### High-Priority Contributions

1. **Monster Library Expansion**:
   - Add more monsters from official sources
   - Improve existing monster stat blocks
   - Validate YAML schema compliance

2. **Spell Mechanics Automation**:
   - Convert spells from `automation: manual` to `automation: full`
   - Implement spell effect handlers
   - Add spell targeting logic

3. **UI/UX Improvements**:
   - Mobile client responsiveness
   - Accessibility features
   - Dark mode support

4. **Testing**:
   - Create unit tests for core functions
   - Integration tests for LAN server
   - End-to-end combat scenarios

5. **Documentation**:
   - Video tutorials
   - Screenshots and GIFs
   - Translated READMEs

### Areas for Improvement

- **Performance optimization** for large combats (20+ creatures)
- **Cross-platform compatibility** testing (macOS, Windows)
- **Authentication system** for internet-exposed instances
- **Undo/redo** functionality for combat actions
- **Import/export** for combat scenarios
- **Sound effects** customization
- **Custom themes** for UI

### Code Contributions

Please ensure:
- Code follows existing style
- Type hints are included
- Docstrings explain complex logic
- No breaking changes to existing YAML schemas
- Test your changes with the full workflow

### Documentation Contributions

- Fix typos and unclear explanations
- Add examples and use cases
- Create guides for specific features
- Translate documentation

### Bug Reports

Use the GitHub issue tracker with:
- Clear title and description
- Steps to reproduce
- Expected vs. actual behavior
- Environment details (OS, Python version)
- Screenshots or logs if applicable

---

## 📄 License

This project is licensed under the MIT License. See the LICENSE file for details.

### Third-Party Assets

- **Monster data**: Derived from AideDD.org with modifications (see `Monsters/README.md`)
- **Spell data**: Compiled from various SRD sources (see `Spells/README.md`)
- **Icons**: Custom emoji-based icons (Unicode standard)
- **Sounds**: Custom audio files

### Copyright Notice

This project is not affiliated with, endorsed by, or sponsored by Wizards of the Coast LLC. Dungeons & Dragons, D&D, and their logos are trademarks of Wizards of the Coast LLC.

This application is a tool for personal use and is not intended for commercial distribution. All monster and spell data is either from the System Reference Document (SRD) or transformed/anonymized to avoid copyright infringement.

---

## 🙏 Acknowledgments

- **Python Community**: For the excellent libraries (FastAPI, Tkinter, PyYAML)
- **D&D Community**: For keeping the game alive and inspiring tools like this
- **AideDD.org**: For providing structured monster data
- **Contributors**: Everyone who has submitted bug reports, feature requests, and code

---

## 📞 Support

- **GitHub Issues**: For bug reports and feature requests
- **Discussions**: For questions and community support
- **Wiki**: For additional documentation and guides

---

## 🚀 Roadmap

Future enhancements under consideration:

- [ ] **Cloud sync**: Save/load combat state across devices
- [ ] **Voice commands**: "Next turn", "Apply 10 damage", etc.
- [ ] **3D dice roller**: Animated dice with physics
- [ ] **Campaign management**: Multiple sessions, long-term tracking
- [ ] **NPC dialogue tracker**: Manage conversations during social encounters
- [ ] **Loot generator**: Random treasure generation
- [ ] **Encounter builder**: CR-based encounter design tool
- [ ] **Music integration**: Background music and sound effects
- [ ] **Virtual tabletop integration**: Sync with Roll20, FoundryVTT, etc.
- [ ] **AI-powered descriptions**: Generate combat narration

---

## 📊 Statistics

*Statistics as of January 2026 (v41):*

- **Total Lines of Code**: ~19,600+ (Python)
- **Monster Library**: 510+ creatures
- **Spell Library**: 390+ spells
- **Supported Conditions**: 15 (2024 Basic Rules)
- **DOT Types**: 3 (Burn, Poison, Necrotic)
- **Terrain Presets**: 7 default types
- **AoE Shapes**: 3 (Circle, Square, Line)
- **Default Players**: 9 example characters

> **Note**: These statistics are approximate and will grow as the project evolves.

---

## ⚠️ Safety and Security Notes

### Local Network Use Only

This LAN server is designed for **trusted local networks** (home Wi-Fi, private table networks). It is **not hardened for internet exposure**.

**Do NOT**:
- Expose the server directly to the internet without proper security
- Use on untrusted public Wi-Fi networks
- Share the LAN URL publicly

**Do**:
- Keep it on your local network
- Use a VPN for remote players
- Set an admin password for DM-only actions
- Review connected sessions regularly

### Data Privacy

- Player data (including IP addresses) is stored locally
- No data is sent to external servers
- Logs contain combat information and may include player names
- Host assignments are saved in `players/.host-assignments.yaml`

### Firewall Configuration

If players cannot connect:
1. Allow Python/the application through your firewall
2. Allow inbound connections on port 8787 (or your chosen port)
3. Ensure your router doesn't block local network communication

---

**Happy gaming! May your rolls be high and your sessions epic! 🎲**