"""
Smartacus Notifications
=======================

Notification services for alerting users about new opportunities.
"""

from .slack_notifier import SlackNotifier

__all__ = ["SlackNotifier"]
