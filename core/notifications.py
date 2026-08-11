"""
Notification and Alert module for FinAnalyzer Enterprise v2.0.0.
Handles SMTP email alerts, in-app notification center, real-time alert rules engine,
and scheduled report delivery.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict, Any, Optional

class NotificationManager:
    """Manages email notifications, in-app alerts, threshold rules, and scheduled deliveries."""

    def __init__(self, smtp_host: str = "smtp.mailtrap.io", smtp_port: int = 2525, smtp_user: str = "", smtp_pass: str = ""):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_pass = smtp_pass
        self.in_app_notifications: List[Dict[str, Any]] = []

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Send professional email notification."""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.smtp_user or "noreply@finanalyzer.enterprise"
            msg['To'] = to_email
            msg['Subject'] = subject

            msg.attach(MIMEText(body, 'html'))

            # In sandbox environments without live SMTP, catch connection exceptions gracefully
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=5)
            if self.smtp_user and self.smtp_pass:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
            server.sendmail(msg['From'], to_email, msg.as_string())
            server.quit()
            return True
        except Exception as e:
            # Fallback for offline/sandboxed environments
            print(f"Email dispatch simulated / caught exception: {e}")
            return False

    def push_in_app_notification(self, user_id: int, title: str, message: str, notification_type: str = "info") -> Dict[str, Any]:
        """Push an in-app notification to the user center."""
        notification = {
            "id": len(self.in_app_notifications) + 1,
            "user_id": user_id,
            "title": title,
            "message": message,
            "type": notification_type,
            "is_read": False,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.in_app_notifications.append(notification)
        return notification

    def evaluate_alert_rules(self, kpis: Dict[str, float], thresholds: Dict[str, float]) -> List[str]:
        """Evaluate real-time financial alert rules (e.g. liquidity warnings, debt limits)."""
        triggered_alerts = []
        for metric, limit in thresholds.items():
            val = kpis.get(metric)
            if val is not None:
                if "ratio" in metric and val < limit:
                    triggered_alerts.append(f"ALERT: {metric} is {val:.2f}, falling below threshold {limit}")
                elif "debt" in metric and val > limit:
                    triggered_alerts.append(f"ALERT: {metric} is {val:.2f}, exceeding safety threshold {limit}")
        return triggered_alerts

    def schedule_report_delivery(self, recipient: str, report_name: str, schedule_cron: str) -> Dict[str, Any]:
        """Mock/register scheduled report delivery task."""
        return {
            "recipient": recipient,
            "report_name": report_name,
            "schedule": schedule_cron,
            "status": "scheduled",
            "registered_at": datetime.utcnow().isoformat()
        }
