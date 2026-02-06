"""
Slack Notifier for Smartacus
============================

Sends notifications to Slack when new opportunities are detected.

Configuration:
    SLACK_WEBHOOK_URL: Slack incoming webhook URL (from .env)
    ENABLE_NOTIFICATIONS: "true" to enable notifications (from .env)

Notification triggers (V2.0 "nouvelle opportunite" definition):
    1. New ASIN first seen in shortlist
    2. Economic event CRITICAL or HIGH detected (< 24h)
    3. Score increased by +10 since last run
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)


class SlackNotifier:
    """
    Sends Slack notifications for new opportunities.

    Uses Slack Incoming Webhooks for simple, stateless notifications.
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        enabled: Optional[bool] = None,
    ):
        """
        Initialize Slack notifier.

        Args:
            webhook_url: Slack webhook URL (default: from SLACK_WEBHOOK_URL env var)
            enabled: Enable notifications (default: from ENABLE_NOTIFICATIONS env var)
        """
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL", "")
        enabled_env = os.getenv("ENABLE_NOTIFICATIONS", "false").lower()
        self.enabled = enabled if enabled is not None else (enabled_env == "true")

        if self.enabled and not self.webhook_url:
            logger.warning("Slack notifications enabled but SLACK_WEBHOOK_URL not set")
            self.enabled = False

    def is_configured(self) -> bool:
        """Check if notifier is properly configured."""
        return bool(self.enabled and self.webhook_url)

    def notify_new_opportunities(
        self,
        opportunities: List[Dict[str, Any]],
        run_id: Optional[str] = None,
        dashboard_url: str = "http://localhost:3000/dashboard",
    ) -> bool:
        """
        Send notification for new opportunities.

        Args:
            opportunities: List of opportunity dicts with keys:
                - asin, title, final_score, window_days, annual_value, urgency, reason
            run_id: Optional pipeline run ID
            dashboard_url: URL to dashboard for "View details" link

        Returns:
            True if notification sent successfully
        """
        if not self.is_configured():
            logger.debug("Slack notifications disabled or not configured")
            return False

        if not opportunities:
            logger.debug("No opportunities to notify")
            return True

        try:
            payload = self._build_message(opportunities, run_id, dashboard_url)
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info(f"Slack notification sent: {len(opportunities)} opportunities")
            return True

        except requests.RequestException as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False

    def _build_message(
        self,
        opportunities: List[Dict[str, Any]],
        run_id: Optional[str],
        dashboard_url: str,
    ) -> Dict[str, Any]:
        """Build Slack message payload."""
        count = len(opportunities)

        # Header
        header = f"*{count} nouvelle{'s' if count > 1 else ''} opportunite{'s' if count > 1 else ''} detectee{'s' if count > 1 else ''}*"

        # Build opportunity list
        opp_lines = []
        for opp in opportunities[:5]:  # Max 5 in notification
            asin = opp.get("asin", "???")
            title = opp.get("title", "")[:40]
            score = opp.get("final_score", 0)
            window = opp.get("window_days", 0)
            value = opp.get("annual_value", 0)
            urgency = opp.get("urgency", "standard").upper()
            reason = opp.get("reason", "")

            # Urgency emoji
            emoji = {
                "CRITICAL": ":red_circle:",
                "HIGH": ":orange_circle:",
                "MEDIUM": ":yellow_circle:",
                "LOW": ":white_circle:",
            }.get(urgency, ":large_blue_circle:")

            line = f"{emoji} *{asin}* | Score {score} | {window}j | ${value:,.0f}/an"
            if reason:
                line += f"\n     _{reason}_"
            opp_lines.append(line)

        if count > 5:
            opp_lines.append(f"_...et {count - 5} autres_")

        # Build blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Smartacus - Nouvelles opportunites",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": header,
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join(opp_lines),
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Voir le dashboard",
                            "emoji": True,
                        },
                        "url": dashboard_url,
                        "style": "primary",
                    }
                ]
            },
        ]

        # Add run info if available
        if run_id:
            blocks.insert(-1, {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Run ID: `{run_id[:8]}` | {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
                    }
                ]
            })

        return {"blocks": blocks}

    def notify_critical_event(
        self,
        asin: str,
        event_type: str,
        thesis: str,
        urgency: str = "HIGH",
    ) -> bool:
        """
        Send immediate notification for critical economic event.

        Use this for CRITICAL or HIGH urgency events that need immediate attention.
        """
        if not self.is_configured():
            return False

        emoji = ":rotating_light:" if urgency == "CRITICAL" else ":warning:"

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} Event {urgency}: {event_type}",
                        "emoji": True,
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*ASIN:* `{asin}`\n*Event:* {event_type}\n*Analyse:* {thesis}",
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Detecte: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
                        }
                    ]
                },
            ]
        }

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Critical event notification sent: {asin} - {event_type}")
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to send critical event notification: {e}")
            return False


def test_slack_notifier():
    """Test Slack notifier with sample data."""
    notifier = SlackNotifier()

    if not notifier.is_configured():
        print("Slack notifier not configured. Set SLACK_WEBHOOK_URL and ENABLE_NOTIFICATIONS=true")
        return

    # Test data
    test_opportunities = [
        {
            "asin": "B08DKHHTFX",
            "title": "VANMASS Car Phone Mount",
            "final_score": 82,
            "window_days": 30,
            "annual_value": 28500,
            "urgency": "HIGH",
            "reason": "New ASIN in shortlist + SUPPLY_SHOCK event",
        },
        {
            "asin": "B0CHYBKQPM",
            "title": "Miracase Phone Holder",
            "final_score": 75,
            "window_days": 45,
            "annual_value": 21000,
            "urgency": "MEDIUM",
            "reason": "Score +12 since last run",
        },
    ]

    success = notifier.notify_new_opportunities(test_opportunities, run_id="test-123")
    print(f"Notification sent: {success}")


if __name__ == "__main__":
    test_slack_notifier()
