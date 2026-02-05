"""
Smartacus Pipeline State Persistence
====================================

Persists scheduler and pipeline state to disk for crash recovery.

On restart, the scheduler can:
- Know when the last successful run happened
- Resume from the last known good state
- Detect missed runs and trigger catch-up

State file format: JSON at DATA_DIR/pipeline_state.json

Usage:
    from src.orchestrator.state import PipelineState

    state = PipelineState()
    state.record_run_start("run-123")
    state.record_run_complete("run-123", "completed", 45.2)
    state.save()

    # After restart:
    state = PipelineState()
    if state.needs_catchup_run():
        trigger_pipeline()
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

DEFAULT_STATE_DIR = Path(__file__).parent.parent.parent / "data"
DEFAULT_STATE_FILE = "pipeline_state.json"


class PipelineState:
    """
    Persistent state for the pipeline scheduler.

    Survives process restarts by writing state to a JSON file.
    """

    def __init__(self, state_dir: Optional[Path] = None):
        self._state_dir = state_dir or Path(
            os.getenv("SMARTACUS_STATE_DIR", str(DEFAULT_STATE_DIR))
        )
        self._state_file = self._state_dir / DEFAULT_STATE_FILE
        self._state: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        """Load state from disk."""
        if self._state_file.exists():
            try:
                with open(self._state_file, "r") as f:
                    data = json.load(f)
                    logger.info(f"Loaded pipeline state from {self._state_file}")
                    return data
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load state file, starting fresh: {e}")

        return {
            "version": 1,
            "last_successful_run": None,
            "last_run": None,
            "consecutive_failures": 0,
            "current_run": None,
            "run_history": [],
        }

    def save(self):
        """Persist state to disk."""
        self._state_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._state_file, "w") as f:
                json.dump(self._state, f, indent=2, default=str)
        except IOError as e:
            logger.error(f"Failed to save state: {e}")

    # =========================================================================
    # Run Lifecycle
    # =========================================================================

    def record_run_start(self, run_id: str):
        """Record that a pipeline run has started."""
        self._state["current_run"] = {
            "run_id": run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
        }
        self.save()

    def record_run_complete(self, run_id: str, status: str, duration_seconds: float):
        """Record that a pipeline run has completed."""
        now = datetime.now(timezone.utc).isoformat()

        run_record = {
            "run_id": run_id,
            "status": status,
            "completed_at": now,
            "duration_seconds": round(duration_seconds, 1),
        }

        # Update last run
        self._state["last_run"] = run_record
        self._state["current_run"] = None

        # Track success/failure
        if status in ("completed", "partial_failure"):
            self._state["last_successful_run"] = run_record
            self._state["consecutive_failures"] = 0
        else:
            self._state["consecutive_failures"] += 1

        # Append to history (keep last 50)
        history = self._state.get("run_history", [])
        history.append(run_record)
        self._state["run_history"] = history[-50:]

        self.save()

    def record_run_failure(self, run_id: str, error: str):
        """Record a run that failed with an error."""
        now = datetime.now(timezone.utc).isoformat()

        run_record = {
            "run_id": run_id,
            "status": "failed",
            "completed_at": now,
            "error": error,
        }

        self._state["last_run"] = run_record
        self._state["current_run"] = None
        self._state["consecutive_failures"] += 1

        history = self._state.get("run_history", [])
        history.append(run_record)
        self._state["run_history"] = history[-50:]

        self.save()

    # =========================================================================
    # Recovery Queries
    # =========================================================================

    @property
    def last_successful_run_at(self) -> Optional[str]:
        """ISO timestamp of last successful run."""
        run = self._state.get("last_successful_run")
        return run["completed_at"] if run else None

    @property
    def consecutive_failures(self) -> int:
        return self._state.get("consecutive_failures", 0)

    @property
    def was_interrupted(self) -> bool:
        """Check if a run was in progress when process stopped."""
        return self._state.get("current_run") is not None

    def needs_catchup_run(self, max_age_hours: float = 26) -> bool:
        """
        Determine if a catch-up run is needed.

        Returns True if:
        - No successful run in last max_age_hours
        - Or previous run was interrupted
        """
        if self.was_interrupted:
            logger.info("Previous run was interrupted, catch-up needed")
            return True

        last = self._state.get("last_successful_run")
        if last is None:
            return True

        try:
            last_time = datetime.fromisoformat(last["completed_at"])
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - last_time).total_seconds() / 3600
            if age_hours > max_age_hours:
                logger.info(f"Last successful run was {age_hours:.1f}h ago, catch-up needed")
                return True
        except (ValueError, KeyError):
            return True

        return False

    def get_summary(self) -> Dict[str, Any]:
        """Get a human-readable state summary."""
        return {
            "last_successful_run": self._state.get("last_successful_run"),
            "last_run": self._state.get("last_run"),
            "consecutive_failures": self.consecutive_failures,
            "was_interrupted": self.was_interrupted,
            "total_runs": len(self._state.get("run_history", [])),
        }
