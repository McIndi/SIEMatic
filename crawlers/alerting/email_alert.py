"""
Email alerting plugin using Django's email functionality.
"""

import logging
from django.core.mail import send_mail
from django.conf import settings
from .base import BaseAlertingPlugin

logger = logging.getLogger(__name__)

class EmailAlert(BaseAlertingPlugin):
    """
    Alerting plugin that sends email notifications for findings.
    """
    name = 'email_alert'

    def send_alert(self, finding):
        subject = f"SIEMatic Alert: {finding.rule_name} - {finding.severity.upper()}"
        message = f"""
Finding Details:
- Rule: {finding.rule_name}
- Severity: {finding.severity}
- Description: {finding.description}
- Event ID: {finding.event.id}
- Created: {finding.created_at}

Event Data: {finding.event.data[:500]}...
"""
        recipients = self.config.get('recipients', [])
        if not recipients:
            logger.warning("No recipients configured for email alert")
            return

        from_email = self.config.get('from_email', settings.DEFAULT_FROM_EMAIL)
        try:
            send_mail(subject, message, from_email, recipients, fail_silently=False)
            logger.info(f"Email alert sent for finding {finding.id} to {recipients}")
        except Exception as e:
            logger.error(f"Failed to send email alert for finding {finding.id}: {e}")