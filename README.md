# D&D Initiative Tracker

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![UI](https://img.shields.io/badge/ui-tkinter-informational)
![LAN](https://img.shields.io/badge/LAN-fastapi%20%2B%20websocket-ffb000)
![License](https://img.shields.io/badge/license-MIT-green)

A desktop-first D&D 5e combat tracker for Dungeon Masters, with an optional local-network web client for players.

- **DM app:** Python + Tkinter desktop UI
- **Player app:** FastAPI + WebSocket mobile web client
- **Data model:** YAML-driven monsters, spells, players, and map presets

> **Important:** the main entry script is intentionally named `dnd_initative_tracker.py` (historical typo kept for compatibility). Do not rename it.

## 📚 Table of Contents

- [What this project does](#what-this-project-does)
- [Architecture at a glance](#architecture-at-a-glance)
- [Quick start](#quick-start)
- [Installation](#installation)
- [Updating and uninstalling](#updating-and-uninstalling)
- [Running the tracker](#running-the-tracker)
- [LAN/mobile client](#lanmobile-client)
  - [Advanced: HTTPS reverse proxy (Caddy + DNS-01)](#advanced-https-reverse-proxy-caddy--dns-01)
- [Map mode](#map-mode)
- [Configuration](#configuration)
- [YAML data files](#yaml-data-files)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Troubleshooting](#troubleshooting)
- [Development and testing](#development-and-testing)
- [Contributing](#contributing)
- [Safety and security](#safety-and-security)
- [License and attribution](#license-and-attribution)

## What this project does

D&D Initiative Tracker is built for running combat quickly at the table while keeping player information synchronized.

### Core DM capabilities

- Add combatants and sort initiative
- Advance rounds/turns with keyboard shortcuts
- Apply damage, healing, and death saves
- Track 2024 Basic Rules conditions and durations
- Open battle map with token movement and terrain costs
- Keep battle and operations logs in `logs/`

### Core player capabilities (LAN mode)

- Join from phone/tablet/laptop browser on local network
- Claim and control assigned character during their turn
- See turn prompts, movement/action counters, and character state
- Equip main-hand/off-hand items from the LAN Inventory button (including shield off-hand +2 AC and fist/unarmed strikes)
- Use map interactions when permitted by DM controls

## Architecture at a glance

The app is intentionally split between desktop UI and LAN server responsibilities:

- **`helper_script.py`**
  - Core Tkinter UI
  - Initiative/combat state management
  - Map mode rendering and tools
- **`dnd_initative_tracker.py`**
  - Main app entry point
  - LAN server lifecycle and client sync
  - Host/player assignment integration
- **`assets/web/lan/`**
  - Player-facing web client
  - State updates over WebSockets
- **Queue-based thread model**
  - Tkinter stays on the main thread
  - LAN server runs in a background thread

## 🚀 Quick start

### Linux / macOS (recommended)

```bash
curl -sSL https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/quick-install.sh | bash
```

Or:

```bash
wget -qO- https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/quick-install.sh | bash
```

### Windows (recommended)

```powershell
irm https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/quick-install.ps1 | iex
```

If execution policy blocks script execution:

```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/quick-install.ps1 | iex"
```

After install, launch the app from your shortcut/launcher and start LAN mode from **LAN → Start LAN Server** when needed.

## Installation

### Prerequisites

- Python **3.9+**
- `pip`
- Git
- Tkinter (often bundled; Linux may need `python3-tk`)

### Manual install (all platforms)

```bash
git clone https://github.com/jeeves-jeevesenson/dnd-initiative-tracker.git
cd dnd-initiative-tracker
python -m venv .venv
```

Activate venv:

- Linux/macOS:
  ```bash
  source .venv/bin/activate
  ```
- Windows:
  ```powershell
  .venv\Scripts\activate
  ```

Install dependencies and run:

```bash
pip install -r requirements.txt
python dnd_initative_tracker.py
```

### Platform notes

- **Linux quick install** places app files in `~/.local/share/dnd-initiative-tracker`
- **Windows quick install** places app files in `%LOCALAPPDATA%\DnDInitiativeTracker`
- Quick install scripts are idempotent and can update an existing install

## Updating and uninstalling

### Updating

You can update from within the app via **Help → Check for Updates**, or run scripts directly.

- Linux/macOS quick-install path:
  ```bash
  cd ~/.local/share/dnd-initiative-tracker
  ./scripts/update-linux.sh
  ```
- Windows quick-install path:
  ```powershell
  cd $env:LOCALAPPDATA\DnDInitiativeTracker
  .\scripts\update-windows.ps1
  ```
- Manual clone installs:
  ```bash
  git pull origin main
  pip install -r requirements.txt
  ```

### Uninstalling

- Linux/macOS:
  ```bash
  curl -sSL https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/uninstall-linux.sh | bash
  ```
- Windows:
  ```powershell
  irm https://raw.githubusercontent.com/jeeves-jeevesenson/dnd-initiative-tracker/main/scripts/uninstall-windows.ps1 | iex
  ```

If manually installed, remove the repository folder and its virtual environment.

## Running the tracker

From a clone:

```bash
python dnd_initative_tracker.py
```

Typical DM flow:

1. Add PCs/monsters and set initiative
2. Sort initiative and start combat
3. Use tools for damage/healing/conditions
4. Open map mode for movement and AoE
5. (Optional) start LAN server for player devices

## LAN/mobile client

LAN mode is optional and intended for trusted local networks.

### Quick setup

1. In DM app: **LAN → Start LAN Server**
2. Share URL via **LAN → Show LAN URL** or **LAN → Show QR Code**
3. Players open URL in browser (same local network)
4. DM can monitor with **LAN → Sessions...**

Default bind settings are in `dnd_initative_tracker.py` (`LanConfig`, default port `8787`).

### Advanced: HTTPS reverse proxy (Caddy + DNS-01)

This section documents a full **advanced LAN HTTPS mode** setup for groups that want players to load the LAN client over HTTPS (for example, `https://dnd.3045.network/`).

Why this exists:

- Browser APIs like web push and service workers require a secure context in many cases.
- HTTPS avoids mixed-content issues when the page itself is loaded securely.
- Caddy handles TLS termination and certificate renewal automatically once configured.

Important non-goal / warning:

- Do **not** publish your DM LAN server directly to the public internet.
- This guide is intended for trusted LAN/VPN environments where your hostname resolves to a private LAN IP.
- DNS-01 validation needs outbound internet access (Let’s Encrypt + DNS API endpoints), but does **not** require opening inbound WAN ports 80/443.

#### Prerequisites and assumptions

Before starting, this guide assumes all of the following:

- You control DNS for your chosen hostnames and have provider API access.
  - `dnd.3045.network` is hosted in Cloudflare.
  - `dnd.iamjeeves.dev` is hosted in Porkbun.
- The DM machine is already running this app and can run the LAN server locally over HTTP (default `8787`).
- Caddy will listen on `:443` and reverse proxy to `http://127.0.0.1:8787` (or your chosen LAN port).
- You can run commands as a user with sudo/root access on Debian/Ubuntu with systemd.

#### 1) DNS records for LAN hostnames (Cloudflare + Porkbun)

Create DNS `A` records that point each hostname at the **private LAN IP** of the DM host.

- Cloudflare zone (`3045.network`):
  - Name: `dnd`
  - Type: `A`
  - Value: `192.168.0.58`
  - Proxy status: **DNS only** (gray cloud)
- Porkbun zone (`iamjeeves.dev`):
  - Name: `dnd`
  - Type: `A`
  - Value: `192.168.1.58`

Cloudflare caveat: RFC1918/private IP targets cannot be used with Cloudflare’s orange-cloud reverse proxy mode. Use DNS-only mode for LAN targets.

##### Multi-subnet caution

If clients are on different subnets without routing between them, one single private IP will not be reachable by everyone.

- `dnd.3045.network -> 192.168.0.58` works for clients that can reach `192.168.0.0/24`.
- `dnd.iamjeeves.dev -> 192.168.1.58` works for clients that can reach `192.168.1.0/24`.
- If you expect cross-subnet access, ensure routing/firewall policy allows traffic between `192.168.0.0/24` and `192.168.1.0/24`, or have users pick the hostname that matches their subnet.

#### 2) Install/prepare Caddy with DNS provider modules using `xcaddy`

Stock distro Caddy builds often do not include every DNS plugin. Build a custom binary with both required modules.

Install Go + `xcaddy` first:

```bash
sudo apt update
sudo apt install -y golang-go caddy
go version
```

```bash
go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest
export PATH="$PATH:$(go env GOPATH)/bin"
xcaddy version
```

If `xcaddy` fails with `go: command not found`, Go is not installed or not in `PATH`. Fix that first.

Build custom Caddy (Cloudflare + Porkbun DNS modules):

```bash
mkdir -p ~/build/caddy && cd ~/build/caddy
xcaddy build \
  --with github.com/caddy-dns/cloudflare \
  --with github.com/caddy-dns/porkbun
```

Replace the system binary safely:

```bash
sudo systemctl stop caddy
sudo cp /usr/bin/caddy "/usr/bin/caddy.bak.$(date +%Y%m%d-%H%M%S)"
sudo install -m 0755 ./caddy /usr/bin/caddy
sudo /usr/bin/caddy version
sudo /usr/bin/caddy list-modules | grep -E 'dns.providers.(cloudflare|porkbun)'
```

Expected module check output should include both:

- `dns.providers.cloudflare`
- `dns.providers.porkbun`

#### 3) Put DNS API secrets in a root-only environment file (systemd)

Create `/etc/caddy/caddy.env` with API credentials (example placeholders):

```bash
sudo tee /etc/caddy/caddy.env >/dev/null <<'EOF'
CF_API_TOKEN=replace_with_cloudflare_dns_edit_token
PORKBUN_API_KEY=replace_with_porkbun_api_key
PORKBUN_API_SECRET_KEY=replace_with_porkbun_api_secret
EOF
```

Set strict permissions:

```bash
sudo chown root:root /etc/caddy/caddy.env
sudo chmod 600 /etc/caddy/caddy.env
```

Create a systemd drop-in so Caddy receives the env vars:

```bash
sudo mkdir -p /etc/systemd/system/caddy.service.d
sudo tee /etc/systemd/system/caddy.service.d/env.conf >/dev/null <<'EOF'
[Service]
EnvironmentFile=/etc/caddy/caddy.env
EOF
sudo systemctl daemon-reload
```

Security reminder:

- Never commit secrets to git.
- Keep `/etc/caddy/caddy.env` readable only by root.
- For Cloudflare, use a scoped token (DNS edit for the target zone), not a global key.

#### 4) Configure Caddyfile for both HTTPS hostnames

Edit `/etc/caddy/Caddyfile` so each hostname gets DNS-01 using its own provider and proxies to local app HTTP.

```caddyfile
dnd.3045.network {
    tls {
        dns cloudflare {env.CF_API_TOKEN}
        resolvers 1.1.1.1 1.0.0.1
    }

    reverse_proxy 127.0.0.1:8787
}

dnd.iamjeeves.dev {
    tls {
        dns porkbun {
            api_key {env.PORKBUN_API_KEY}
            api_secret_key {env.PORKBUN_API_SECRET_KEY}
        }
        resolvers 1.1.1.1 8.8.8.8
    }

    reverse_proxy 127.0.0.1:8787
}
```

Notes:

- Replace `8787` if your LAN server uses another port.
- Explicit `resolvers` can help avoid local DNS resolver oddities during TXT validation.
- Caddy `reverse_proxy` supports WebSockets; if the page is served over HTTPS, browser WebSocket traffic will use `wss://` automatically.

Load/reload Caddy:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

#### 5) Verification checklist (cert issuance + app reachability)

Watch Caddy status/logs:

```bash
sudo systemctl status caddy --no-pager
sudo journalctl -u caddy -f
```

During first issuance, logs should show DNS-01 challenge attempts (for example, messages about trying to solve challenge `dns-01`) and then successful certificate obtain/install events.

Use `curl` with **GET** (not only HEAD):

```bash
curl -v https://dnd.3045.network/
curl -v https://dnd.iamjeeves.dev/
```

Why not rely only on `curl -I`? `-I` sends a HEAD request, and some app routes may return `405 Method Not Allowed` for HEAD even when normal GET page loads are fine.

Browser checks on a player device:

- Certificate is valid (Let’s Encrypt chain, no warning page).
- No mixed-content errors in browser devtools console.
- WebSocket session is connected over `wss://`.
- `window.isSecureContext === true` in devtools console.

#### 6) Configure the DM app URL settings to match the proxy

After HTTPS proxying works, configure the in-app LAN URL behavior:

1. In DM app menu, open **LAN → URL Mode → HTTP / HTTPS / Both**.
2. Recommended default: choose **Both** for proxy-safe behavior.
3. Set HTTPS URL in **LAN → Set HTTPS Public URL…**.
   - On `192.168.0.x` side, enter `https://dnd.3045.network/`
   - On `192.168.1.x` side, enter `https://dnd.iamjeeves.dev/`
4. Share connection details via **LAN → Show LAN URL** or **LAN → Show QR Code**.

Persistence details:

- By default, settings save to `~/Documents/Dnd-Init-Yamls/settings/lan_url.json`.
- If `INITTRACKER_DATA_DIR` is set, the same relative path is used under that directory: `<INITTRACKER_DATA_DIR>/settings/lan_url.json`.

#### 7) Troubleshooting

- `module not registered: dns.providers.cloudflare` or `dns.providers.porkbun`
  - You are likely running stock Caddy instead of the custom `xcaddy` build.
  - Re-check binary replacement and module list:
    ```bash
    caddy list-modules | grep -E 'dns.providers.(cloudflare|porkbun)'
    ```
- DNS-01 propagation errors/timeouts
  - Verify token/key permissions and zone access.
  - Confirm hostname is in the expected DNS zone.
  - Keep explicit `resolvers` in the `tls` blocks.
- Clients cannot connect
  - Confirm domain resolves to the subnet-reachable private IP for that client.
  - Verify inter-subnet routing/firewall policy if crossing `192.168.0.0/24` and `192.168.1.0/24`.
  - Verify host firewall allows inbound `443/tcp` from LAN.
- Upstream mismatch or 502 errors
  - Confirm DM LAN server is running.
  - Confirm app LAN port (default `8787`) and match `reverse_proxy 127.0.0.1:<port>`.

### LAN rules Help viewer (local PDF)

The LAN client includes a **Help** modal that can open your own local rules PDF.

- Default PDF location: `~/Documents/Dnd-Init-Yamls/rules/PlayersHandbook2024.pdf`
- Optional override: set `INITTRACKER_RULES_PDF` to an absolute or relative file path.
- LAN routes used by the Help UI:
  - `GET /rules.pdf`
  - `GET /api/rules/status`
  - `GET /api/rules/toc`

> The project does **not** ship with any rulebook PDFs. You must provide your own local copy in the runtime data folder.

### Optional startup behavior

You can change startup behavior in `dnd_initative_tracker.py`:

```python
POC_AUTO_START_LAN = True
POC_AUTO_SEED_PCS = True
```

### iOS/iPadOS web push

For iOS web push support:

- iOS/iPadOS 16.4+
- Add web app to Home Screen
- Enable notifications in iOS settings

### Browser push notifications (turn alerts)

Turn alerts now have two delivery paths:

- **Foreground/hidden-tab alerts (no push required):** if the LAN tab is open but hidden/inactive, turn checks still run and can fire a local browser notification.
- **True background alerts (Web Push):** if the browser supports push and the player is subscribed, the DM host can send push notifications even when the page is not active.

Requirements for Web Push:

- Run the LAN client from a secure context (`https://`), or from loopback/local development as supported by the browser.
- Configure VAPID keys on the DM host:
  - `INITTRACKER_VAPID_PUBLIC_KEY`
  - `INITTRACKER_VAPID_PRIVATE_KEY`
  - Optional: `INITTRACKER_VAPID_SUBJECT` (defaults to `mailto:dm@example.com`)
- Ensure dependencies are installed from `requirements.txt` (includes `pywebpush`).

Player setup:

- Join LAN client and claim a character.
- Open **Settings → Notifications → Enable** (this grants permission and syncs the push subscription to the DM host).
- **Enable Turn Alerts** uses the same subscription/sync path.
- On iOS/iPadOS, install to Home Screen before enabling notifications.

## Map mode

Map mode provides a grid-based battle area with turn-aware movement.

Key capabilities:

- Drag-and-drop token movement
- Terrain painting (rough/swim-capable presets)
- Obstacle placement
- AoE overlays (circle/square/line)
- Optional background image support (Pillow)

### Session snapshots (DM)

- Use **Session → Save Session…** to write a full DM-side session snapshot as JSON.
- Default save folder: `~/Documents/Dnd-Init-Yamls/sessions`.
- Use **Session → Load Session…** to restore a snapshot.
- Use **Session → New Session** to clear current DM session state (combat/map/log) without modifying YAML files.
- **Quick Save** / **Quick Load** use `~/Documents/Dnd-Init-Yamls/sessions/quick_save.json`.
- Session snapshots are separate from YAML content and do **not** modify `players/*.yaml`, `Monsters/*.yaml`, or other data definitions.

## Configuration

Primary runtime toggles are in `dnd_initative_tracker.py`.

Commonly adjusted settings:

- LAN bind host/port/admin password (`LanConfig`)
- Auto-start LAN and auto-seed PCs
- Host assignment behavior

You can also customize defaults in `helper_script.py`:

- `DEFAULT_STARTING_PLAYERS`
- `DEFAULT_ROUGH_TERRAIN_PRESETS`
- `DAMAGE_TYPES`

## YAML data files

This project is data-driven; YAML content controls most game data.

- Runtime YAML data is stored in a client-local folder:
  - Windows: `~/Documents/Dnd-Init-Yamls`
  - Linux: `~/Documents/Dnd-Init-Yamls`
- `Monsters/*.yaml` — monster stat blocks (copied to local folder on first run)
- `Spells/*.yaml` — spell definitions/mechanics (copied to local folder on first run)
- `players/*.yaml` — player character defaults (copied to local folder on first run)
- `Items/Weapons/*.yaml` / `Items/Armor/*.yaml` — structured item definitions (draft schema, copied to local folder on first run)
- `presets/` — terrain/obstacle presets

See schema docs:

- [`Monsters/README.md`](Monsters/README.md)
- [`Spells/README.md`](Spells/README.md)
- [`players/README.md`](players/README.md)

### File/folder naming note (Linux)

Keep directory casing exactly as expected:

- `Monsters/` (capital `M`)
- `Spells/` (capital `S`)

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Space` | Next turn |
| `Shift+Space` | Previous turn |
| `d` | Damage tool |
| `h` | Heal tool |
| `c` | Conditions tool |
| `t` | Death saves / DOT tool |
| `p` | Open map mode |

## Troubleshooting

### `No module named fastapi`

```bash
pip install fastapi "uvicorn[standard]"
```

### `No module named qrcode` or PIL errors

```bash
pip install qrcode pillow
```

### `Tkinter` missing on Linux

```bash
sudo apt install python3-tk
```

### Players cannot connect in LAN mode

Check:

1. Devices are on the same network
2. Firewall allows chosen LAN port (default `8787`)
3. URL points to host machine local IP
4. DM app LAN server is actually running

## 🧪 Development and testing

### Repository layout

- `dnd_initative_tracker.py` — app entry point + LAN integration
- `helper_script.py` — core UI/combat logic
- `assets/web/` — LAN web client files
- `scripts/` — install/update/uninstall and smoke-test scripts
- `tests/` — Python test suite

### Local setup

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

### Validation commands

```bash
python -m compileall .
python -m pytest
```

If you modify LAN/web behavior, run LAN smoke tooling in `scripts/` (for example `scripts/lan-smoke-playwright.py`).

## Contributing

Contributions are welcome via pull requests.

Please keep changes:

- small and reviewable
- backward compatible (especially YAML schemas and LAN payload expectations)
- documented when behavior changes

For bug reports, include:

- OS + Python version
- exact repro steps
- expected vs actual behavior
- relevant logs/screenshots

## ⚠️ Safety and security

- LAN server is designed for **trusted local networks only**
- Do **not** expose directly to the public internet
- For remote sessions, use VPN and your own access controls
- Player/IP assignment data stays local on the host machine

## License and attribution

- Project license: **MIT**
- Vendored LAN rules viewer assets include **PDF.js** (`pdfjs-dist 3.11.174`) under `assets/web/lan/pdfjs/`, licensed under **Apache License 2.0** (see `assets/web/lan/pdfjs/LICENSE`)
- Not affiliated with Wizards of the Coast
- Data/source notes are documented in folder-specific READMEs

Happy gaming, and good luck behind the screen.
