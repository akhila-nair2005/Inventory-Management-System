from django.db.models.signals import post_save
from django.dispatch import receiver

from inventory.models import Product
from .models import StockAlert, EmailLog
from .services import dispatch_email, get_alert_recipients


@receiver(post_save, sender=Product)
def check_low_stock(sender, instance, **kwargs):
    """Create / escalate a stock alert whenever a product is at or below its reorder level."""
    if not instance.is_low_stock:
        return

    new_type = (
        StockAlert.AlertType.OUT_OF_STOCK if instance.quantity == 0
        else StockAlert.AlertType.LOW_STOCK
    )
    active = StockAlert.objects.filter(product=instance, resolved=False).first()

    if active is None:
        alert = StockAlert.objects.create(
            product=instance,
            alert_type=new_type,
            quantity_at_alert=instance.quantity,
            reorder_level_at_alert=instance.reorder_level,
        )
        notify_stock_alert(alert)
    elif active.alert_type == StockAlert.AlertType.LOW_STOCK and new_type == StockAlert.AlertType.OUT_OF_STOCK:
        # Was running low, has now hit zero: escalate and notify again.
        active.alert_type = new_type
        active.quantity_at_alert = instance.quantity
        active.save(update_fields=['alert_type', 'quantity_at_alert'])
        notify_stock_alert(active)


def notify_stock_alert(alert):
    """Tell Admins, Managers and Staff (the people who restock) about the alert."""
    product = alert.product
    supplier_name = product.supplier.name if product.supplier else 'not set'

    if alert.alert_type == StockAlert.AlertType.OUT_OF_STOCK:
        subject = f"[OUT OF STOCK] {product.name} ({product.sku})"
        body = (
            f"Product '{product.name}' (SKU: {product.sku}) has reached 0 units.\n"
            f"Supplier: {supplier_name}\n"
            f"Suggested reorder quantity: {product.suggested_reorder_quantity}\n\n"
            f"Immediate purchase order recommended."
        )
        log_type = EmailLog.AlertType.OUT_OF_STOCK
    else:
        subject = f"[LOW STOCK] {product.name} ({alert.quantity_at_alert} units left)"
        body = (
            f"Product '{product.name}' (SKU: {product.sku}) has dropped to "
            f"{alert.quantity_at_alert} units, at or below its reorder level of "
            f"{alert.reorder_level_at_alert} units.\n"
            f"Supplier: {supplier_name}\n"
            f"Suggested reorder quantity: {product.suggested_reorder_quantity}\n\n"
            f"Please arrange a restock soon."
        )
        log_type = EmailLog.AlertType.LOW_STOCK

    dispatch_email(
        subject=subject,
        body=body,
        recipients=get_alert_recipients(),
        alert_type=log_type,
        product=product,
    )


# Kept so any older import of notify_low_stock keeps working.
notify_low_stock = notify_stock_alert
