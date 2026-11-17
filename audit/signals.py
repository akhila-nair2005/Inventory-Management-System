from decimal import Decimal

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from billing.models import Invoice
from inventory.models import Product
from .middleware import get_current_user_id
from .models import AuditLog

# Fields compared on every save, per model
TRACKED_FIELDS = {
    Product: ['name', 'brand', 'sku', 'barcode', 'category_id', 'supplier_id', 'price',
              'cost_price', 'quantity', 'reorder_level', 'max_stock_level'],
    Invoice: ['customer_id', 'status', 'payment_method', 'tax_percent', 'discount_amount'],
}
# Changes limited to these fields are routine "updates" (stock moved, invoice paid);
# anything else means a person edited the record's details.
ROUTINE_FIELDS = {'quantity', 'status'}


def log_action(instance, action, user_id=None, changes=None):
    if user_id is None:
        user_id = get_current_user_id()
    AuditLog.objects.create(
        user_id=user_id,
        action=action,
        model_name=instance.__class__.__name__,
        object_id=str(instance.pk),
        object_repr=str(instance),
        changes=changes or None,
    )


def _norm(value):
    """Compare 119900 and Decimal('119900.00') as equal; leave other values as text."""
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return format(Decimal(str(value)).normalize(), 'f')
    return str(value)


def _snapshot(sender, instance):
    """Remember the stored values before an existing row is overwritten."""
    instance._audit_before = None
    if instance.pk:
        instance._audit_before = (
            sender.objects.filter(pk=instance.pk).values(*TRACKED_FIELDS[sender]).first()
        )


def _log_save(sender, instance, created, fallback_user_id=None):
    if created:
        log_action(instance, AuditLog.Action.CREATE, user_id=fallback_user_id)
        return

    before = getattr(instance, '_audit_before', None) or {}
    changes = {}
    for field in TRACKED_FIELDS[sender]:
        old, new = before.get(field), getattr(instance, field)
        if field in before and _norm(old) != _norm(new):
            changes[field] = [_norm(old), _norm(new)]

    if not changes:        # nothing really changed: don't clutter the log
        return
    action = AuditLog.Action.UPDATE if set(changes) <= ROUTINE_FIELDS else AuditLog.Action.EDIT
    log_action(instance, action, changes=changes)


@receiver(pre_save, sender=Product)
def snapshot_product(sender, instance, **kwargs):
    _snapshot(Product, instance)


@receiver(post_save, sender=Product)
def log_product_save(sender, instance, created, **kwargs):
    _log_save(Product, instance, created)


@receiver(post_delete, sender=Product)
def log_product_delete(sender, instance, **kwargs):
    log_action(instance, AuditLog.Action.DELETE)


@receiver(pre_save, sender=Invoice)
def snapshot_invoice(sender, instance, **kwargs):
    _snapshot(Invoice, instance)


@receiver(post_save, sender=Invoice)
def log_invoice_save(sender, instance, created, **kwargs):
    _log_save(Invoice, instance, created, fallback_user_id=instance.created_by_id)


@receiver(post_delete, sender=Invoice)
def log_invoice_delete(sender, instance, **kwargs):
    log_action(instance, AuditLog.Action.DELETE)
