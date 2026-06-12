from __future__ import annotations
"""
ManusClaw Self-Update System
==============================
Checks for updates from GitHub and applies them without manual intervention.

Usage:
  from app.update import UpdateManager
  mgr = UpdateManager()
  result = mgr.check_and_update()
"""
import subprocess
import sys
from typing import Optional
from pathlib import Path

from app.logger import logger


class UpdateManager:
    """Manages self-updates for ManusClaw from the Git repository."""

    def __init__(self, repo_dir: Optional[str] = None) -> None:
        self.repo_dir = repo_dir or str(Path(__file__).resolve().parent.parent)

    def check_for_updates(self) -> dict:
        """Check if a newer version is available on the remote.

        Returns:
            dict with keys: has_update (bool), current (str), remote (str), error (str|None)
        """
        try:
            # Get current commit
            current = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, cwd=self.repo_dir, timeout=10,
            )
            if current.returncode != 0:
                return {"has_update": False, "current": "unknown", "remote": "unknown",
                        "error": f"git rev-parse failed: {current.stderr.strip()}"}

            current_hash = current.stdout.strip()[:12]

            # Fetch latest
            fetch = subprocess.run(
                ["git", "fetch", "origin", "main"],
                capture_output=True, text=True, cwd=self.repo_dir, timeout=30,
            )
            if fetch.returncode != 0:
                return {"has_update": False, "current": current_hash, "remote": "unknown",
                        "error": f"git fetch failed: {fetch.stderr.strip()}"}

            # Get remote commit
            remote = subprocess.run(
                ["git", "rev-parse", "origin/main"],
                capture_output=True, text=True, cwd=self.repo_dir, timeout=10,
            )
            remote_hash = remote.stdout.strip()[:12]

            has_update = current_hash != remote_hash

            # Get version tags if available
            current_tag = self._get_tag(current_hash)
            remote_tag = self._get_tag(remote_hash)

            return {
                "has_update": has_update,
                "current": current_tag or current_hash,
                "remote": remote_tag or remote_hash,
                "error": None,
            }
        except Exception as e:
            return {"has_update": False, "current": "unknown", "remote": "unknown",
                    "error": str(e)}

    def apply_update(self) -> dict:
        """Apply the update by pulling latest changes and reinstalling.

        Returns:
            dict with keys: success (bool), message (str), error (str|None)
        """
        try:
            # Stash any local changes
            subprocess.run(
                ["git", "stash"], capture_output=True, cwd=self.repo_dir, timeout=10,
            )

            # Pull latest
            pull = subprocess.run(
                ["git", "pull", "origin", "main"],
                capture_output=True, text=True, cwd=self.repo_dir, timeout=60,
            )
            if pull.returncode != 0:
                return {"success": False, "message": "Pull failed",
                        "error": pull.stderr.strip()}

            # Reinstall dependencies
            install = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", "."],
                capture_output=True, text=True, cwd=self.repo_dir, timeout=120,
            )
            if install.returncode != 0:
                logger.warning(f"[Update] pip install warning: {install.stderr[:200]}")

            # Pop stashed changes
            subprocess.run(
                ["git", "stash", "pop"], capture_output=True, cwd=self.repo_dir, timeout=10,
            )

            return {
                "success": True,
                "message": f"Updated successfully. {pull.stdout.strip()}",
                "error": None,
            }
        except Exception as e:
            return {"success": False, "message": "Update failed", "error": str(e)}

    def check_and_update(self, auto_apply: bool = False) -> dict:
        """Check for updates and optionally apply them.

        Args:
            auto_apply: If True, automatically apply the update without asking.

        Returns:
            dict with update check results and apply results if applied.
        """
        check = self.check_for_updates()

        if not check["has_update"]:
            return {**check, "applied": False, "message": "Already up to date."}

        if auto_apply:
            logger.info(f"[Update] New version available: {check['remote']}. Auto-applying...")
            apply_result = self.apply_update()
            return {**check, "applied": apply_result["success"],
                    "message": apply_result["message"], "error": apply_result["error"]}

        return {**check, "applied": False,
                "message": f"Update available: {check['current']} → {check['remote']}. "
                           f"Call apply_update() to install."}

    def _get_tag(self, commit_hash: str) -> Optional[str]:
        """Get the version tag for a commit, if any."""
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--exact-match", commit_hash],
                capture_output=True, text=True, cwd=self.repo_dir, timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None
