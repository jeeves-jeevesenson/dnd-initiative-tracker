#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

APPDIR="${APPDIR:-$HOME/.local/share/dnd-initiative-tracker}"
ICON_NAME="inittracker"
ICON_BASE="$HOME/.local/share/icons/hicolor"
DESKTOP_FILE="$HOME/.local/share/applications/inittracker.desktop"
WRAPPER="${APPDIR}/launch-inittracker.sh"
PYTHON_BIN="${PYTHON:-/usr/bin/python3}"

if ! command -v rsync >/dev/null 2>&1; then
  echo "Error: rsync is required to install the app." >&2
  exit 1
fi

echo "Installing D&D Initiative Tracker to ${APPDIR}..."

mkdir -p "${APPDIR}"
rsync -a --delete \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude "__pycache__" \
  "${REPO_DIR}/" "${APPDIR}/"

mkdir -p "${APPDIR}/logs"

cat > "${WRAPPER}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${APPDIR}/logs"
PYTHON_BIN="${PYTHON:-/usr/bin/python3}"

mkdir -p "${LOG_DIR}"
nohup "${PYTHON_BIN}" "${APPDIR}/dnd_initative_tracker.py" >> "${LOG_DIR}/launcher.log" 2>&1 &

echo "D&D Initiative Tracker launched."
echo "Logs: ${LOG_DIR}/launcher.log"
EOF

chmod +x "${WRAPPER}"

if [[ -f "${APPDIR}/assets/graphic-512.png" ]]; then
  install -Dm644 \
    "${APPDIR}/assets/graphic-512.png" \
    "${ICON_BASE}/512x512/apps/${ICON_NAME}.png"
  echo "Installed 512x512 icon."
fi

if [[ -f "${APPDIR}/assets/graphic-192.png" ]]; then
  install -Dm644 \
    "${APPDIR}/assets/graphic-192.png" \
    "${ICON_BASE}/192x192/apps/${ICON_NAME}.png"
  echo "Installed 192x192 icon."
fi

mkdir -p "$(dirname "${DESKTOP_FILE}")"
cat > "${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Name=D&D Initiative Tracker
Comment=Run the D&D Initiative Tracker
Exec=${WRAPPER}
Icon=${ICON_NAME}
Terminal=false
Type=Application
Categories=Game;Utility;
StartupNotify=true
EOF

echo "Installed desktop entry: ${DESKTOP_FILE}"

if command -v kbuildsycoca5 >/dev/null 2>&1; then
  kbuildsycoca5 >/dev/null 2>&1 || true
  echo "Refreshed KDE desktop cache."
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${HOME}/.local/share/applications" >/dev/null 2>&1 || true
  echo "Updated desktop database."
fi

echo "Install complete!"
echo "Launch from your desktop menu or run:"
echo "  ${WRAPPER}"
echo "Logs are stored in: ${APPDIR}/logs/launcher.log"
