#!/bin/bash
# Update script for D&D Initiative Tracker (Linux/macOS)
# This script updates the application to the latest version from GitHub

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
TEMP_DIR="/tmp/dnd-tracker-update-$$"
YAML_DIRS=("Monsters" "Spells" "players" "presets")
YAML_BACKUP_DIR="$TEMP_DIR/yaml_backup"

echo "=========================================="
echo "D&D Initiative Tracker - Update"
echo "=========================================="
echo ""

# Function to cleanup temp files
cleanup() {
    if [ -d "$TEMP_DIR" ]; then
        echo "Cleaning up temporary files..."
        rm -rf "$TEMP_DIR"
        echo "✓ Cleanup complete"
    fi
}

# Register cleanup on exit
trap cleanup EXIT

# Check if we're in the right directory
if [ ! -f "$INSTALL_DIR/dnd_initative_tracker.py" ]; then
    echo "Error: Could not find D&D Initiative Tracker installation"
    echo "Expected location: $INSTALL_DIR"
    exit 1
fi

echo "Installation directory: $INSTALL_DIR"
echo ""

# Check if git is available
if ! command -v git &> /dev/null; then
    echo "Error: git is not installed. Please install git first."
    exit 1
fi

# Check if this is a git repository
if [ ! -d "$INSTALL_DIR/.git" ]; then
    echo "Error: This installation was not installed via git."
    echo "Please re-install using the quick-install script to enable updates."
    exit 1
fi

echo "Checking for updates..."
cd "$INSTALL_DIR"

# Fetch latest changes
DEFAULT_REMOTE="origin"
if ! git remote get-url "$DEFAULT_REMOTE" >/dev/null 2>&1; then
    DEFAULT_REMOTE=$(git remote | head -n 1)
fi
if [ -z "$DEFAULT_REMOTE" ] || ! git remote get-url "$DEFAULT_REMOTE" >/dev/null 2>&1; then
    echo "Error: No valid git remotes found to check for updates."
    exit 1
fi

git fetch "$DEFAULT_REMOTE" --prune --tags

# Check if there are updates
LOCAL_COMMIT=$(git rev-parse HEAD)
DEFAULT_BRANCH_REF=$(git symbolic-ref -q "refs/remotes/${DEFAULT_REMOTE}/HEAD" 2>/dev/null || true)
DEFAULT_BRANCH_NAME="${DEFAULT_BRANCH_REF#refs/remotes/${DEFAULT_REMOTE}/}"
if [ -z "$DEFAULT_BRANCH_NAME" ]; then
    echo "Warning: Could not detect remote default branch; falling back to 'main'."
    echo "         Run 'git remote set-head ${DEFAULT_REMOTE} --auto' to configure it."
fi
DEFAULT_BRANCH_NAME="${DEFAULT_BRANCH_NAME:-main}"
# Set UPDATE_BRANCH in your environment to override the default branch.
# Accepts "remote/branch" or a branch name that will be prefixed with the default remote.
REMOTE_BRANCH="${UPDATE_BRANCH:-${DEFAULT_REMOTE}/${DEFAULT_BRANCH_NAME}}"
case "$REMOTE_BRANCH" in
    */*) ;;
    *) REMOTE_BRANCH="${DEFAULT_REMOTE}/${REMOTE_BRANCH}" ;;
esac
if ! git rev-parse --verify "${REMOTE_BRANCH}" >/dev/null 2>&1; then
    echo "Error: Could not resolve update branch ${REMOTE_BRANCH}."
    echo "Try again after fetching or set UPDATE_BRANCH to a valid remote branch (e.g., ${DEFAULT_REMOTE}/${DEFAULT_BRANCH_NAME})."
    exit 1
fi
REMOTE_COMMIT=$(git rev-parse "$REMOTE_BRANCH")

if [ "$LOCAL_COMMIT" = "$REMOTE_COMMIT" ]; then
    echo ""
    echo "✓ You are already up to date!"
    exit 0
fi

echo "✓ Updates available"
echo ""

# Show what will be updated
echo "Changes to be applied:"
git log --oneline --decorate -n 5 "HEAD..${REMOTE_BRANCH}"
echo ""

# Ask for confirmation
read -p "Do you want to update? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Update cancelled"
    exit 0
fi

echo ""
echo "Updating application..."

# Backup YAML files to preserve local customizations
echo "Backing up YAML files..."
mkdir -p "$YAML_BACKUP_DIR"
for yaml_dir in "${YAML_DIRS[@]}"; do
    if [ -d "$INSTALL_DIR/$yaml_dir" ]; then
        while IFS= read -r -d '' file; do
            rel_path="${file#$INSTALL_DIR/}"
            mkdir -p "$YAML_BACKUP_DIR/$(dirname "$rel_path")"
            cp "$file" "$YAML_BACKUP_DIR/$rel_path"
            git checkout -- "$rel_path" 2>/dev/null || true
        done < <(find "$INSTALL_DIR/$yaml_dir" -type f \( -name "*.yaml" -o -name "*.yml" \) -print0)
    fi
done

# Pull latest changes
REMOTE_NAME="${REMOTE_BRANCH%%/*}"
REMOTE_BRANCH_PATH="${REMOTE_BRANCH#${REMOTE_NAME}/}"
if [ -z "$REMOTE_NAME" ] || [ -z "$REMOTE_BRANCH_PATH" ] || ! git remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    echo "Error: Unable to determine update remote/branch from ${REMOTE_BRANCH}."
    echo "       Expected format: remote/branch and a configured git remote."
    exit 1
fi
git pull "$REMOTE_NAME" "$REMOTE_BRANCH_PATH"

# Update dependencies
if [ -f "$INSTALL_DIR/.venv/bin/activate" ]; then
    echo ""
    echo "Updating dependencies..."
    source "$INSTALL_DIR/.venv/bin/activate"
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    echo "✓ Dependencies updated"
fi

# Restore YAML files to keep local customizations
if [ -d "$YAML_BACKUP_DIR" ]; then
    echo ""
    echo "Restoring local YAML files..."
    while IFS= read -r -d '' file; do
        rel_path="${file#$YAML_BACKUP_DIR/}"
        mkdir -p "$INSTALL_DIR/$(dirname "$rel_path")"
        cp "$file" "$INSTALL_DIR/$rel_path"
    done < <(find "$YAML_BACKUP_DIR" -type f -print0)
    echo "✓ Local YAML files restored"
fi

echo ""
echo "=========================================="
echo "✓ Update complete!"
echo "=========================================="
echo ""
echo "You can now restart the D&D Initiative Tracker to use the updated version."
echo ""
