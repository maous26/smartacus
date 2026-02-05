"""
Smartacus Pipeline Scheduler
============================

Provides scheduling capabilities for the daily pipeline execution.
Supports both cron-based scheduling and APScheduler.

Features:
    - Daily execution at configurable time (default: 6:00 AM UTC)
    - Manual trigger support
    - Run history tracking
    - Health monitoring integration

Usage:
    # Start scheduler daemon
    python -m src.orchestrator.scheduler

    # Or use programmatically
    from src.orchestrator.scheduler import PipelineScheduler

    scheduler = PipelineScheduler()
    scheduler.start()

Configuration:
    SCHEDULER_CRON_HOUR: Hour for daily run (default: 6)
    SCHEDULER_CRON_MINUTE: Minute for daily run (default: 0)
    SCHEDULER_TIMEZONE: Timezone (default: UTC)
"""

import os
import signal
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass, field
from threading import Event
import json

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.events import (
        EVENT_JOB_EXECUTED,
        EVENT_JOB_ERROR,
        EVENT_JOB_MISSED,
        JobExecutionEvent,
    )
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False

from .daily_pipeline import DailyPipeline, PipelineResult, PipelineStatus

# Configure logging
logger = logging.getLogger(__name__)


def get_env_int(key: str, default: int) -> int:
    """Get environment variable as integer."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass
class SchedulerConfig:
    """Scheduler configuration."""

    # Cron schedule for daily run
    cron_hour: int = field(default_factory=lambda: get_env_int("SCHEDULER_CRON_HOUR", 6))
    cron_minute: int = field(default_factory=lambda: get_env_int("SCHEDULER_CRON_MINUTE", 0))
    timezone: str = field(default_factory=lambda: os.getenv("SCHEDULER_TIMEZONE", "UTC"))

    # Retry settings
    max_retries: int = field(default_factory=lambda: get_env_int("SCHEDULER_MAX_RETRIES", 3))
    retry_delay_minutes: int = field(default_factory=lambda: get_env_int("SCHEDULER_RETRY_DELAY", 30))

    # Timeout settings (in seconds)
    job_timeout: int = field(default_factory=lambda: get_env_int("SCHEDULER_JOB_TIMEOUT", 7200))  # 2 hours

    # Misfire grace time (seconds to consider a missed job)
    misfire_grace_time: int = field(default_factory=lambda: get_env_int("SCHEDULER_MISFIRE_GRACE", 3600))

    def get_cron_expression(self) -> str:
        """Get cron expression for logging."""
        return f"{self.cron_minute} {self.cron_hour} * * *"


@dataclass
class RunHistory:
    """Tracks scheduler run history."""
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
    last_run_duration: Optional[float] = None
    consecutive_failures: int = 0
    total_runs: int = 0
    total_successes: int = 0
    total_failures: int = 0

    def record_run(self, status: PipelineStatus, duration: float):
        """Record a pipeline run."""
        self.last_run_at = datetime.utcnow()
        self.last_run_status = status.value
        self.last_run_duration = duration
        self.total_runs += 1

        if status in (PipelineStatus.COMPLETED, PipelineStatus.PARTIAL_FAILURE):
            self.total_successes += 1
            self.consecutive_failures = 0
        else:
            self.total_failures += 1
            self.consecutive_failures += 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_run_status": self.last_run_status,
            "last_run_duration": self.last_run_duration,
            "consecutive_failures": self.consecutive_failures,
            "total_runs": self.total_runs,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "success_rate": (
                self.total_successes / self.total_runs * 100
                if self.total_runs > 0 else 0
            ),
        }


class PipelineScheduler:
    """
    Scheduler for the Smartacus daily pipeline.

    Manages automated execution of the daily pipeline at configured times.
    Supports both APScheduler-based scheduling and simple cron integration.
    """

    def __init__(self, config: Optional[SchedulerConfig] = None):
        """
        Initialize the scheduler.

        Args:
            config: Scheduler configuration (uses defaults if None)
        """
        self.config = config or SchedulerConfig()
        self._scheduler: Optional[BackgroundScheduler] = None
        self._stop_event = Event()
        self._history = RunHistory()
        self._on_complete_callback: Optional[Callable[[PipelineResult], None]] = None

        logger.info(
            f"PipelineScheduler initialized: "
            f"schedule={self.config.get_cron_expression()} {self.config.timezone}"
        )

    @property
    def is_running(self) -> bool:
        """Check if scheduler is currently running."""
        if self._scheduler is None:
            return False
        return self._scheduler.running

    def set_on_complete_callback(self, callback: Callable[[PipelineResult], None]):
        """
        Set callback to be invoked when pipeline completes.

        Args:
            callback: Function that receives PipelineResult
        """
        self._on_complete_callback = callback

    # =========================================================================
    # APScheduler-based Scheduling
    # =========================================================================

    def start(self, blocking: bool = False):
        """
        Start the scheduler.

        Args:
            blocking: If True, blocks until scheduler is stopped
        """
        if not HAS_APSCHEDULER:
            raise RuntimeError(
                "APScheduler is required for scheduled execution. "
                "Install with: pip install apscheduler"
            )

        if self._scheduler is not None and self._scheduler.running:
            logger.warning("Scheduler is already running")
            return

        self._scheduler = BackgroundScheduler(timezone=self.config.timezone)

        # Add the daily pipeline job
        self._scheduler.add_job(
            self._execute_pipeline,
            trigger=CronTrigger(
                hour=self.config.cron_hour,
                minute=self.config.cron_minute,
                timezone=self.config.timezone,
            ),
            id="daily_pipeline",
            name="Smartacus Daily Pipeline",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=self.config.misfire_grace_time,
        )

        # Add event listeners
        self._scheduler.add_listener(
            self._on_job_executed,
            EVENT_JOB_EXECUTED
        )
        self._scheduler.add_listener(
            self._on_job_error,
            EVENT_JOB_ERROR
        )
        self._scheduler.add_listener(
            self._on_job_missed,
            EVENT_JOB_MISSED
        )

        # Start the scheduler
        self._scheduler.start()
        logger.info(
            f"Scheduler started. Next run at: "
            f"{self._get_next_run_time()}"
        )

        if blocking:
            self._run_blocking()

    def stop(self, wait: bool = True):
        """
        Stop the scheduler.

        Args:
            wait: If True, waits for running jobs to complete
        """
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=wait)
            self._scheduler = None
            logger.info("Scheduler stopped")

        self._stop_event.set()

    def _run_blocking(self):
        """Block until stop signal received."""
        # Setup signal handlers
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, stopping scheduler...")
            self.stop()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        logger.info("Scheduler running in blocking mode. Press Ctrl+C to stop.")
        self._stop_event.wait()

    def trigger_now(self) -> Optional[PipelineResult]:
        """
        Trigger an immediate pipeline run.

        Returns:
            PipelineResult if successful, None otherwise
        """
        logger.info("Triggering immediate pipeline run")
        return self._execute_pipeline()

    def _execute_pipeline(self) -> Optional[PipelineResult]:
        """Execute the daily pipeline."""
        logger.info("=== Scheduled Pipeline Execution Starting ===")

        try:
            with DailyPipeline() as pipeline:
                result = pipeline.run()

                # Update history
                self._history.record_run(
                    result.status,
                    result.duration_seconds or 0
                )

                # Invoke callback if set
                if self._on_complete_callback:
                    try:
                        self._on_complete_callback(result)
                    except Exception as e:
                        logger.warning(f"Callback failed: {e}")

                return result

        except Exception as e:
            logger.exception(f"Pipeline execution failed: {e}")
            self._history.record_run(PipelineStatus.FAILED, 0)

            # Check for consecutive failures
            if self._history.consecutive_failures >= self.config.max_retries:
                logger.error(
                    f"Pipeline has failed {self._history.consecutive_failures} "
                    f"consecutive times. Manual intervention required."
                )
            else:
                # Schedule retry
                self._schedule_retry()

            return None

    def _schedule_retry(self):
        """Schedule a retry after failure."""
        if self._scheduler is None:
            return

        retry_time = datetime.utcnow() + timedelta(
            minutes=self.config.retry_delay_minutes
        )

        self._scheduler.add_job(
            self._execute_pipeline,
            trigger="date",
            run_date=retry_time,
            id=f"retry_{datetime.utcnow().timestamp()}",
            name="Pipeline Retry",
            max_instances=1,
        )

        logger.info(f"Scheduled retry at {retry_time}")

    def _get_next_run_time(self) -> Optional[datetime]:
        """Get the next scheduled run time."""
        if self._scheduler is None:
            return None

        job = self._scheduler.get_job("daily_pipeline")
        if job is None:
            return None

        return job.next_run_time

    def _on_job_executed(self, event: 'JobExecutionEvent'):
        """Handle successful job execution."""
        logger.info(f"Job {event.job_id} executed successfully")

    def _on_job_error(self, event: 'JobExecutionEvent'):
        """Handle job execution error."""
        logger.error(
            f"Job {event.job_id} raised an exception: {event.exception}"
        )

    def _on_job_missed(self, event: 'JobExecutionEvent'):
        """Handle missed job execution."""
        logger.warning(f"Job {event.job_id} missed its scheduled time")

    # =========================================================================
    # Status and Monitoring
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """
        Get current scheduler status.

        Returns:
            Status dictionary with scheduler state and history
        """
        return {
            "is_running": self.is_running,
            "config": {
                "schedule": self.config.get_cron_expression(),
                "timezone": self.config.timezone,
                "max_retries": self.config.max_retries,
                "retry_delay_minutes": self.config.retry_delay_minutes,
            },
            "next_run": (
                self._get_next_run_time().isoformat()
                if self._get_next_run_time() else None
            ),
            "history": self._history.to_dict(),
        }

    def get_run_history(self) -> RunHistory:
        """Get run history."""
        return self._history


# =============================================================================
# Cron Integration
# =============================================================================

def generate_cron_entry(
    python_path: str = "python",
    module_path: str = "-m src.orchestrator.cli run",
    log_file: str = "/var/log/smartacus/pipeline.log",
    hour: int = 6,
    minute: int = 0,
) -> str:
    """
    Generate a crontab entry for the pipeline.

    Args:
        python_path: Path to Python interpreter
        module_path: Module path to execute
        log_file: Path for log output
        hour: Hour for execution (0-23)
        minute: Minute for execution (0-59)

    Returns:
        Crontab entry string

    Example:
        print(generate_cron_entry())
        # Output: 0 6 * * * python -m src.orchestrator.cli run >> /var/log/smartacus/pipeline.log 2>&1
    """
    return f"{minute} {hour} * * * {python_path} {module_path} >> {log_file} 2>&1"


def generate_systemd_timer() -> Dict[str, str]:
    """
    Generate systemd timer and service unit files content.

    Returns:
        Dictionary with 'timer' and 'service' unit file contents

    Example usage:
        units = generate_systemd_timer()
        # Save units['timer'] to /etc/systemd/system/smartacus-pipeline.timer
        # Save units['service'] to /etc/systemd/system/smartacus-pipeline.service
    """
    service_unit = """[Unit]
Description=Smartacus Daily Pipeline
After=network.target postgresql.service

[Service]
Type=oneshot
User=smartacus
Group=smartacus
WorkingDirectory=/opt/smartacus
ExecStart=/opt/smartacus/venv/bin/python -m src.orchestrator.cli run
StandardOutput=journal
StandardError=journal
TimeoutStartSec=7200

[Install]
WantedBy=multi-user.target
"""

    timer_unit = """[Unit]
Description=Run Smartacus Daily Pipeline

[Timer]
OnCalendar=*-*-* 06:00:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
"""

    return {
        "service": service_unit,
        "timer": timer_unit,
    }


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    """Command-line entry point for scheduler."""
    import argparse

    parser = argparse.ArgumentParser(description="Smartacus Pipeline Scheduler")
    parser.add_argument(
        "--mode",
        choices=["daemon", "once", "status", "cron-entry", "systemd-units"],
        default="daemon",
        help="Scheduler mode"
    )
    parser.add_argument(
        "--hour",
        type=int,
        default=6,
        help="Hour for scheduled run (0-23)"
    )
    parser.add_argument(
        "--minute",
        type=int,
        default=0,
        help="Minute for scheduled run (0-59)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if args.mode == "daemon":
        if not HAS_APSCHEDULER:
            print("Error: APScheduler is required for daemon mode.")
            print("Install with: pip install apscheduler")
            return 1

        config = SchedulerConfig(
            cron_hour=args.hour,
            cron_minute=args.minute,
        )
        scheduler = PipelineScheduler(config)
        scheduler.start(blocking=True)

    elif args.mode == "once":
        scheduler = PipelineScheduler()
        result = scheduler.trigger_now()
        if result:
            print(f"\nPipeline completed: {result.status.value}")
            print(f"Duration: {result.duration_seconds:.1f}s")
            print(f"Opportunities: {result.opportunities_above_threshold}")
        else:
            print("Pipeline execution failed")
            return 1

    elif args.mode == "status":
        scheduler = PipelineScheduler()
        status = scheduler.get_status()
        print(json.dumps(status, indent=2, default=str))

    elif args.mode == "cron-entry":
        entry = generate_cron_entry(hour=args.hour, minute=args.minute)
        print("Add the following to your crontab (crontab -e):")
        print(entry)

    elif args.mode == "systemd-units":
        units = generate_systemd_timer()
        print("=== smartacus-pipeline.service ===")
        print(units["service"])
        print("\n=== smartacus-pipeline.timer ===")
        print(units["timer"])
        print("\nSave these files and run:")
        print("  sudo systemctl daemon-reload")
        print("  sudo systemctl enable smartacus-pipeline.timer")
        print("  sudo systemctl start smartacus-pipeline.timer")

    return 0


if __name__ == "__main__":
    exit(main())
