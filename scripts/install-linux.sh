#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

APPDIR="${APPDIR:-$HOME/.local/share/dnd-initiative-tracker}"
ICON_NAME="inittracker"
ICON_BASE="$HOME/.local/share/icons/hicolor"
DESKTOP_FILE="$HOME/.local/share/applications/inittracker.desktop"
WRAPPER="${APPDIR}/launch-inittracker.sh"
LAUNCHER="${HOME}/.local/bin/dnd-initiative-tracker"
PYTHON_BIN="${PYTHON:-/usr/bin/python3}"
VENV_DIR="${APPDIR}/.venv"
INSTALL_DESKTOP_ENTRY="${INSTALL_DESKTOP_ENTRY:-}"

if ! command -v rsync >/dev/null 2>&1; then
  echo "Error: rsync is required to install the app." >&2
  exit 1
fi

echo "Installing D&D Initiative Tracker to ${APPDIR}..."

mkdir -p "${APPDIR}"
if [[ "$(cd "${APPDIR}" && pwd)" != "$(cd "${REPO_DIR}" && pwd)" ]]; then
  rsync -a --delete \
    --exclude ".git" \
    --exclude ".venv" \
    --exclude "__pycache__" \
    "${REPO_DIR}/" "${APPDIR}/"
else
  echo "Install directory matches repository; skipping file sync."
fi

mkdir -p "${APPDIR}/logs"

if [[ "${INSTALL_PIP_DEPS:-0}" == "1" || ! -d "${VENV_DIR}" ]]; then
  if [[ ! -d "${VENV_DIR}" ]]; then
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  fi
fi

if [[ "${INSTALL_PIP_DEPS:-0}" == "1" ]]; then
  if [[ -f "${APPDIR}/requirements.txt" ]]; then
    "${VENV_DIR}/bin/pip" install -r "${APPDIR}/requirements.txt"
  else
    echo "Warning: requirements.txt not found; skipping pip install."
  fi
fi

cat > "${WRAPPER}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${APPDIR}/logs"
PYTHON_BIN="${PYTHON:-/usr/bin/python3}"
VENV_PYTHON="${APPDIR}/.venv/bin/python"

if [[ -x "${VENV_PYTHON}" ]]; then
  PYTHON_BIN="${VENV_PYTHON}"
fi

mkdir -p "${LOG_DIR}"
cd "${APPDIR}"
nohup "${PYTHON_BIN}" "${APPDIR}/dnd_initative_tracker.py" >> "${LOG_DIR}/launcher.log" 2>&1 &

echo "D&D Initiative Tracker launched."
echo "Logs: ${LOG_DIR}/launcher.log"
EOF

chmod +x "${WRAPPER}"

mkdir -p "$(dirname "${LAUNCHER}")"
cat > "${LAUNCHER}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
"${WRAPPER}" "\$@"
EOF

chmod +x "${LAUNCHER}"

if [[ ":${PATH}:" != *":${HOME}/.local/bin:"* ]]; then
  echo ""
  echo "⚠️  Note: ${HOME}/.local/bin is not in your PATH"
  echo "   Add this line to your ~/.bashrc or ~/.zshrc:"
  echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
  echo ""
fi

install_desktop_entry=false
if [[ -n "${INSTALL_DESKTOP_ENTRY}" ]]; then
  if [[ "${INSTALL_DESKTOP_ENTRY}" == "1" || "${INSTALL_DESKTOP_ENTRY}" == "true" || "${INSTALL_DESKTOP_ENTRY}" == "yes" ]]; then
    install_desktop_entry=true
  fi
else
  desktop_choice=""
  if [[ -t 0 ]]; then
    read -r -p "Install a KDE/desktop launcher entry? [y/N]: " desktop_choice
  elif [[ -r /dev/tty ]]; then
    read -r -p "Install a KDE/desktop launcher entry? [y/N]: " desktop_choice </dev/tty
  fi
  if [[ "${desktop_choice}" =~ ^[Yy]$ ]]; then
    install_desktop_entry=true
  fi
fi

if [[ "${install_desktop_entry}" == "true" ]]; then
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
Path=${APPDIR}
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
else
  echo "Skipping desktop entry setup."
fi

echo "Install complete!"
echo "Launch from your desktop menu or run:"
echo "  ${WRAPPER}"
echo "  ${LAUNCHER}"
echo "Logs are stored in: ${APPDIR}/logs/launcher.log"
