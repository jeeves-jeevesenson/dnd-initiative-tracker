#!/usr/bin/env bash
set -euo pipefail

APPDIR="${APPDIR:-$HOME/.local/share/dnd-initiative-tracker}"
LAUNCHER="$HOME/.local/bin/dnd-initiative-tracker"
ICON_NAME="inittracker"
ICON_BASE="$HOME/.local/share/icons/hicolor"
DESKTOP_FILE="$HOME/.local/share/applications/inittracker.desktop"
ICON_512="${ICON_BASE}/512x512/apps/${ICON_NAME}.png"
ICON_192="${ICON_BASE}/192x192/apps/${ICON_NAME}.png"

if [[ -d "${APPDIR}" ]]; then
  rm -rf "${APPDIR}"
  echo "Removed install directory: ${APPDIR}"
else
  echo "Install directory already removed: ${APPDIR}"
fi

if [[ -f "${LAUNCHER}" ]]; then
  rm -f "${LAUNCHER}"
  echo "Removed launcher: ${LAUNCHER}"
else
  echo "Launcher already removed: ${LAUNCHER}"
fi

if [[ -f "${ICON_512}" ]]; then
  rm -f "${ICON_512}"
  echo "Removed 512x512 icon: ${ICON_512}"
else
  echo "512x512 icon already removed: ${ICON_512}"
fi

if [[ -f "${ICON_192}" ]]; then
  rm -f "${ICON_192}"
  echo "Removed 192x192 icon: ${ICON_192}"
else
  echo "192x192 icon already removed: ${ICON_192}"
fi

if [[ -f "${DESKTOP_FILE}" ]]; then
  rm -f "${DESKTOP_FILE}"
  echo "Removed desktop entry: ${DESKTOP_FILE}"
else
  echo "Desktop entry already removed: ${DESKTOP_FILE}"
fi

if command -v kbuildsycoca5 >/dev/null 2>&1; then
  kbuildsycoca5 >/dev/null 2>&1 || true
  echo "Refreshed KDE desktop cache."
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${HOME}/.local/share/applications" >/dev/null 2>&1 || true
  echo "Updated desktop database."
fi

echo "Uninstall complete!"
