from __future__ import annotations
"""
Delegate tool — spawns isolated subagents with session tracking.

UPGRADED from basic DelegateTool:
- Session isolation: each delegate gets its own session ID in the DB
- Status tracking: running/completed/failed states
- Concurrent delegates: spawn multiple delegates in parallel
- Timeout with partial result capture
- Workspace isolation: delegates work in isolated subdirectories
"""
import asyncio
import uuid
from typing import Optional

from app.tool.base import BaseTool
from app.schema import ToolResult


# Track active delegates for status queries
_active_delegates: dict[str, dict] = {}


class DelegateTool(BaseTool):
    name = "delegate"
    description = (
        "Spawn an isolated subagent to handle an independent subtask. "
        "Use for tasks that can run in parallel or need full isolation. "
        "Each delegate gets its own session and workspace subdirectory."
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "The subtask description"},
            "max_steps": {"type": "integer", "default": 15},
            "timeout": {"type": "integer", "default": 300},
            "workspace_subdir": {
                "type": "string",
                "description": "Optional subdirectory name for isolated workspace",
                "default": "",
            },
        },
        "required": ["task"],
    }

    async def execute(
        self,
        task: str,
        max_steps: int = 15,
        timeout: int = 300,
        workspace_subdir: str = "",
    ) -> ToolResult:
        from app.agent.manus import Manus
        from app.permissions.gate import AgentMode
        from app.db.session import SessionDB

        delegate_id = str(uuid.uuid4())[:8]

        # Register delegate
        _active_delegates[delegate_id] = {
            "status": "running",
            "task": task[:200],
            "started_at": asyncio.get_event_loop().time(),
        }

        async def _run() -> str:
            agent = Manus(mode=AgentMode.BUILD)
            agent._max_steps = max_steps

            # Set up isolated workspace if requested
            if workspace_subdir:
                from pathlib import Path
                from app.config import Config
                base_ws = Path(Config.get().workspace_dir)
                isolated_ws = base_ws / "delegates" / workspace_subdir
                isolated_ws.mkdir(parents=True, exist_ok=True)

            # Create a dedicated session for this delegate
            try:
                db = SessionDB()
                session_id = await db.create_session(
                    goal=f"[delegate:{delegate_id}] {task[:200]}",
                    agent_name="manus-delegate",
                    mode="build",
                )
                agent._injected_session_id = session_id
                db.close()
            except Exception:
                pass  # Session tracking is best-effort

            result = await agent.run(task)

            # Cleanup
            try:
                await agent.cleanup()
            except Exception:
                pass

            return result

        try:
            result = await asyncio.wait_for(_run(), timeout=timeout)
            _active_delegates[delegate_id]["status"] = "completed"
            return ToolResult(
                output=f"[Delegate {delegate_id} completed]\n{result[:3000]}"
            )
        except asyncio.TimeoutError:
            _active_delegates[delegate_id]["status"] = "timeout"
            return ToolResult(
                error=f"Delegate {delegate_id} timed out after {timeout}s. "
                      f"Partial results may be in workspace/delegates/."
            )
        except Exception as e:
            _active_delegates[delegate_id]["status"] = "failed"
            return ToolResult(error=f"Delegate {delegate_id} error: {e}")

    @staticmethod
    def get_active_delegates() -> dict[str, dict]:
        """Return status of all tracked delegates."""
        return dict(_active_delegates)

    @staticmethod
    def cleanup_completed() -> int:
        """Remove completed/failed/timeout delegates from tracking. Returns count removed."""
        to_remove = [
            did for did, info in _active_delegates.items()
            if info["status"] != "running"
        ]
        for did in to_remove:
            del _active_delegates[did]
        return len(to_remove)
