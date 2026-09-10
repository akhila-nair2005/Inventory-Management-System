from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from inventory.models import Product
from accounts.models import User
from .models import StockAlert


@receiver(post_save, sender=Product)
def check_low_stock(sender, instance, **kwargs):
    if instance.is_low_stock:
        exists = StockAlert.objects.filter(product=instance, resolved=False).exists()
        if not exists:
            alert = StockAlert.objects.create(
                product=instance,
                quantity_at_alert=instance.quantity,
                reorder_level_at_alert=instance.reorder_level,
            )
            notify_low_stock(alert)


def notify_low_stock(alert):
    """
    Notifies Managers and Staff (the people responsible for restocking)
    when a product hits its reorder level.
    """
    recipients = User.objects.filter(role__in=['MANAGER', 'STAFF']).exclude(email='')
    recipient_emails = list(recipients.values_list('email', flat=True))

    if recipient_emails:
        send_mail(
            subject=f"Low Stock Alert: {alert.product.name}",
            message=(
                f"Product '{alert.product.name}' (SKU: {alert.product.sku}) has dropped to "
                f"{alert.quantity_at_alert} units — at or below its reorder level of "
                f"{alert.reorder_level_at_alert} units.\n\n"
                f"Please arrange a restock soon."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_emails,
            fail_silently=True,
        )