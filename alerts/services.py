"""Central place for sending e-mail through SMTP and recording it in EmailLog."""
from django.conf import settings
from django.core.mail import EmailMessage

from accounts.models import User
from .models import EmailLog


def get_alert_recipients(roles=('ADMIN', 'MANAGER', 'STAFF')):
    """E-mail addresses of active users holding one of the given roles."""
    return list(
        User.objects.filter(role__in=roles, is_active=True)
        .exclude(email='')
        .values_list('email', flat=True)
        .distinct()
    )


def dispatch_email(subject, body, recipients, alert_type, product=None,
                   triggered_by=None, attachments=None):
    """
    Send one e-mail and write one EmailLog row per recipient.

    `attachments` is an optional list of (filename, bytes, mimetype) tuples.
    Returns True if the message was handed to the mail backend without error.
    Never raises, so a mail problem can never break stock updates or invoicing.
    """
    recipients = [r for r in dict.fromkeys(recipients or []) if r]
    if not recipients:
        return False

    status, error = EmailLog.Status.SENT, ''
    try:
        message = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        for filename, content, mimetype in (attachments or []):
            message.attach(filename, content, mimetype)
        message.send(fail_silently=False)
    except Exception as exc:  # SMTP down, bad credentials, etc.
        status, error = EmailLog.Status.FAILED, str(exc)[:255]

    EmailLog.objects.bulk_create([
        EmailLog(
            recipient_email=r,
            subject=subject[:255],
            body=body,
            alert_type=alert_type,
            status=status,
            error_message=error,
            product=product,
            triggered_by=triggered_by,
        )
        for r in recipients
    ])
    return status == EmailLog.Status.SENT
