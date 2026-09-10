from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from inventory.models import Product, StockMovement
from billing.models import Invoice
from .models import AuditLog

# Models you want to track
TRACKED_MODELS = [Product, StockMovement, Invoice]


def log_action(instance, action, user=None):
    AuditLog.objects.create(
        user=user,
        action=action,
        model_name=instance.__class__.__name__,
        object_id=str(instance.pk),
        object_repr=str(instance),
    )


@receiver(post_save, sender=Product)
def log_product_save(sender, instance, created, **kwargs):
    log_action(instance, AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE)


@receiver(post_delete, sender=Product)
def log_product_delete(sender, instance, **kwargs):
    log_action(instance, AuditLog.Action.DELETE)


@receiver(post_save, sender=Invoice)
def log_invoice_save(sender, instance, created, **kwargs):
    log_action(instance, AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE)


@receiver(post_delete, sender=Invoice)
def log_invoice_delete(sender, instance, **kwargs):
    log_action(instance, AuditLog.Action.DELETE)