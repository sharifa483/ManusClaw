from __future__ import annotations
"""
ManusClaw Session Manager
==========================
Advanced session management with isolated, named, and persistent sessions.

Features:
- Named sessions: create sessions with custom keys for persistence
- Session isolation: each session has its own context/workspace
- Session listing and search
- Session cleanup for old sessions
- Cross-session search integration
"""
import asyncio
import time
from typing import Optional

from app.db.session import SessionDB
from app.logger import logger


class SessionManager:
    """Manages agent sessions with advanced features."""

    def __init__(self) -> None:
        self.db = SessionDB()

    async def create_named_session(
        self, name: str, goal: str, agent_name: str = "manus", mode: str = "build"
    ) -> str:
        """Create a session with a human-readable name for later retrieval.

        Args:
            name: A unique name for this session (e.g., "project-alpha-research")
            goal: The session goal/prompt
            agent_name: Which agent type to use
            mode: Permission mode

        Returns:
            Session ID
        """
        session_id = await self.db.create_session(
            goal=f"[{name}] {goal}", agent_name=agent_name, mode=mode
        )
        logger.info(f"[SessionManager] Created named session '{name}' -> {session_id}")
        return session_id

    async def list_recent_sessions(self, limit: int = 20) -> list[dict]:
        """List recent sessions with metadata.

        Returns:
            List of session dicts with id, goal, state, step_count, created_at
        """
        try:
            rows = await self.db.list_sessions(limit=limit)
            return [dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error(f"[SessionManager] List sessions error: {e}")
            return []

    async def get_session(self, session_id: str) -> Optional[dict]:
        """Get a session by ID."""
        try:
            row = await self.db.get_session(session_id)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"[SessionManager] Get session error: {e}")
            return None

    async def cleanup_old_sessions(self, max_age_hours: int = 168) -> int:
        """Clean up sessions older than max_age_hours.

        Args:
            max_age_hours: Maximum age in hours (default 168 = 7 days)

        Returns:
            Number of sessions cleaned up
        """
        cutoff = time.time() - (max_age_hours * 3600)
        try:
            count = await self.db.cleanup_sessions(before_ts=cutoff)
            if count:
                logger.info(f"[SessionManager] Cleaned up {count} old sessions")
            return count
        except Exception as e:
            logger.error(f"[SessionManager] Cleanup error: {e}")
            return 0

    async def get_session_stats(self) -> dict:
        """Get aggregate session statistics."""
        try:
            sessions = await self.list_recent_sessions(limit=1000)
            total = len(sessions)
            states = {}
            for s in sessions:
                state = s.get("state", "unknown")
                states[state] = states.get(state, 0) + 1
            return {
                "total": total,
                "by_state": states,
            }
        except Exception:
            return {"total": 0, "by_state": {}}

    def close(self) -> None:
        self.db.close()
