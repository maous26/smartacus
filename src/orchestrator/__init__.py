"""
Smartacus Orchestrator Module
=============================

Orchestration layer for the Smartacus pipeline.

Components:
    - DailyPipeline: Main orchestrator for daily execution
    - PipelineScheduler: Scheduling and automation
    - CLI: Command-line interface

Usage:
    from src.orchestrator import DailyPipeline

    with DailyPipeline() as pipeline:
        result = pipeline.run()
"""

from .daily_pipeline import (
    DailyPipeline,
    PipelineResult,
    PipelineStatus,
    PipelineStage,
    StageResult,
)
from .scheduler import (
    PipelineScheduler,
    SchedulerConfig,
    RunHistory,
)

__all__ = [
    # Pipeline
    "DailyPipeline",
    "PipelineResult",
    "PipelineStatus",
    "PipelineStage",
    "StageResult",
    # Scheduler
    "PipelineScheduler",
    "SchedulerConfig",
    "RunHistory",
]
