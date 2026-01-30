"""
Update checker module for D&D Initiative Tracker.
Checks for updates from GitHub releases and main branch.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from typing import Optional, Tuple, Dict
import logging

logger = logging.getLogger(__name__)

# GitHub repository information
REPO_OWNER = "jeeves-jeevesenson"
REPO_NAME = "dnd-initiative-tracker"
GITHUB_API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"


def get_current_version() -> str:
    """Get the current version of the application."""
    version_file = os.path.join(os.path.dirname(__file__), "VERSION")
    try:
        with open(version_file, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        # Fallback to APP_VERSION from main file if VERSION file doesn't exist
        return "41"


def check_latest_release() -> Optional[Dict]:
    """Check GitHub for the latest release.
    
    Returns:
        Dict with 'tag_name', 'name', 'html_url', 'published_at' if available, None otherwise
    """
    try:
        url = f"{GITHUB_API_BASE}/releases/latest"
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github.v3+json")
        
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            return {
                "tag_name": data.get("tag_name", ""),
                "name": data.get("name", ""),
                "html_url": data.get("html_url", ""),
                "published_at": data.get("published_at", ""),
                "body": data.get("body", "")
            }
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        logger.debug(f"Could not check latest release: {e}")
        return None


def check_main_branch_commit() -> Optional[Dict]:
    """Check GitHub for the latest commit on main branch.
    
    Returns:
        Dict with 'sha', 'commit' info if available, None otherwise
    """
    try:
        url = f"{GITHUB_API_BASE}/commits/main"
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github.v3+json")
        
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            return {
                "sha": data.get("sha", ""),
                "short_sha": data.get("sha", "")[:7],
                "message": data.get("commit", {}).get("message", ""),
                "author": data.get("commit", {}).get("author", {}).get("name", ""),
                "date": data.get("commit", {}).get("author", {}).get("date", ""),
                "html_url": data.get("html_url", "")
            }
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        logger.debug(f"Could not check main branch: {e}")
        return None


def get_local_git_commit() -> Optional[str]:
    """Get the current local git commit SHA if in a git repository.
    
    Returns:
        Short commit SHA (7 chars) if available, None otherwise
    """
    try:
        import subprocess
        git_dir = os.path.join(os.path.dirname(__file__), ".git")
        if not os.path.exists(git_dir):
            return None
        
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=os.path.dirname(__file__),
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"Could not get local git commit: {e}")
    return None


def check_for_updates() -> Tuple[bool, str, Optional[Dict]]:
    """Check for available updates.
    
    Returns:
        Tuple of (has_update, message, update_info)
        - has_update: True if an update is available
        - message: Human-readable message about the update status
        - update_info: Dict with update details or None
    """
    current_version = get_current_version()
    local_commit = get_local_git_commit()
    
    # Check for latest release
    latest_release = check_latest_release()
    
    # Check main branch for updates
    latest_commit = check_main_branch_commit()
    
    # Determine if updates are available
    if latest_release:
        # Extract version number from tag (e.g., "v41" -> "41")
        release_version = latest_release["tag_name"].lstrip("v")
        try:
            if int(release_version) > int(current_version):
                message = f"New release available: {latest_release['tag_name']}\n"
                message += f"Current version: v{current_version}\n"
                if latest_release.get("name"):
                    message += f"\nRelease: {latest_release['name']}"
                return True, message, {"type": "release", "data": latest_release}
        except ValueError:
            pass
    
    # If we're in a git repo, check if main branch has newer commits
    if local_commit and latest_commit:
        if latest_commit["short_sha"] != local_commit:
            message = f"New commits available on main branch\n"
            message += f"Your commit: {local_commit}\n"
            message += f"Latest commit: {latest_commit['short_sha']}\n"
            message += f"Message: {latest_commit['message'][:60]}..."
            return True, message, {"type": "commit", "data": latest_commit}
    
    # No updates available
    message = f"You are up to date! (v{current_version})"
    if local_commit:
        message += f"\nCommit: {local_commit}"
    return False, message, None


def get_update_command() -> Optional[str]:
    """Get the appropriate update command for the current platform and installation type.
    
    Returns:
        Command string to run for updating, or None if not applicable
    """
    script_dir = os.path.dirname(__file__)
    
    # Check if we're in a standard installation location
    if sys.platform.startswith("win"):
        # Windows installation
        install_dir = os.path.join(os.getenv("LOCALAPPDATA", ""), "DnDInitiativeTracker")
        if script_dir.startswith(install_dir):
            update_script = os.path.join(script_dir, "scripts", "update-windows.ps1")
            if os.path.exists(update_script):
                return f'powershell -ExecutionPolicy Bypass -File "{update_script}"'
    else:
        # Linux/macOS installation
        home_dir = os.path.expanduser("~")
        install_dir = os.path.join(home_dir, ".local", "share", "dnd-initiative-tracker")
        if script_dir.startswith(install_dir):
            update_script = os.path.join(script_dir, "scripts", "update-linux.sh")
            if os.path.exists(update_script):
                return f'bash "{update_script}"'
    
    return None
