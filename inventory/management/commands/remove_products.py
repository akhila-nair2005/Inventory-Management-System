"""
Remove products and everything that depends on them.

    python manage.py remove_products pencil pen "rice bag" --dry-run     (preview only)
    python manage.py remove_products pencil pen "rice bag"               (do it)

For each product this deletes: its stock movements, stock alerts, e-mail log rows and audit entries;
its purchase-order lines and goods-receipt lines; its invoice lines. Purchase orders and invoices that
contained ONLY these products are deleted completely (including their goods receipts). Orders and
invoices that also contain other products are kept, just without the removed lines.
Customers are only removed with --remove-customers (and only if they are left with no invoices).
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from audit.models import AuditLog
from alerts.models import StockAlert
from billing.models import Customer, Invoice, InvoiceItem
from inventory.models import (
    GoodsReceipt, GoodsReceiptItem, Product, PurchaseOrder, PurchaseOrderItem, StockMovement,
)

try:
    from alerts.models import EmailLog
except ImportError:          # older database / code without the e-mail log
    EmailLog = None


class Command(BaseCommand):
    help = "Delete products (matched by name, case-insensitive) together with all related data."

    def add_arguments(self, parser):
        parser.add_argument('names', nargs='+', help='Product names, e.g. pencil pen "rice bag"')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted, change nothing.')
        parser.add_argument('--remove-customers', action='store_true',
                            help='Also delete customers left with no invoices after the cleanup.')

    def handle(self, *args, **opts):
        wanted = [n.strip().lower() for n in opts['names']]
        products = [p for p in Product.objects.all() if p.name.strip().lower() in wanted]
        found = {p.name.strip().lower() for p in products}
        missing = [n for n in wanted if n not in found]
        if missing:
            self.stdout.write(self.style.WARNING(f"Not found (skipped): {', '.join(missing)}"))
        if not products:
            raise CommandError("No matching products.")
        ids = [p.pk for p in products]

        po_ids = set(PurchaseOrderItem.objects.filter(product_id__in=ids).values_list('purchase_order_id', flat=True))
        po_keep = set(PurchaseOrderItem.objects.filter(purchase_order_id__in=po_ids).exclude(product_id__in=ids)
                      .values_list('purchase_order_id', flat=True))
        po_delete = po_ids - po_keep

        inv_ids = set(InvoiceItem.objects.filter(product_id__in=ids).values_list('invoice_id', flat=True))
        inv_keep = set(InvoiceItem.objects.filter(invoice_id__in=inv_ids).exclude(product_id__in=ids)
                       .values_list('invoice_id', flat=True))
        inv_delete = inv_ids - inv_keep

        plan = [
            ("products", len(ids)),
            ("stock movements", StockMovement.objects.filter(product_id__in=ids).count()),
            ("stock alerts", StockAlert.objects.filter(product_id__in=ids).count()),
            ("purchase orders (whole order)", len(po_delete)),
            ("purchase-order lines", PurchaseOrderItem.objects.filter(product_id__in=ids).count()),
            ("goods-receipt lines", GoodsReceiptItem.objects.filter(po_item__product_id__in=ids).count()),
            ("invoices (whole invoice)", len(inv_delete)),
            ("invoice lines", InvoiceItem.objects.filter(product_id__in=ids).count()),
        ]
        self.stdout.write("Products: " + ", ".join(p.name for p in products))
        for label, n in plan:
            self.stdout.write(f"  {label:32} {n}")
        if opts['dry_run']:
            self.stdout.write(self.style.SUCCESS("Dry run only: nothing was changed."))
            return

        with transaction.atomic():
            str_ids = [str(i) for i in ids]
            AuditLog.objects.filter(model_name='Product', object_id__in=str_ids).delete()
            AuditLog.objects.filter(model_name='Invoice', object_id__in=[str(i) for i in inv_delete]).delete()
            AuditLog.objects.filter(model_name='PurchaseOrder', object_id__in=[str(i) for i in po_delete]).delete()

            GoodsReceiptItem.objects.filter(po_item__product_id__in=ids).delete()
            GoodsReceiptItem.objects.filter(receipt__purchase_order_id__in=po_delete).delete()
            GoodsReceipt.objects.filter(purchase_order_id__in=po_delete).delete()
            PurchaseOrderItem.objects.filter(product_id__in=ids).delete()
            PurchaseOrder.objects.filter(pk__in=po_delete).delete()

            customer_ids = set(Invoice.objects.filter(pk__in=inv_delete, customer__isnull=False)
                               .values_list('customer_id', flat=True))
            InvoiceItem.objects.filter(product_id__in=ids).delete()
            Invoice.objects.filter(pk__in=inv_delete).delete()
            if opts['remove_customers']:
                for cid in customer_ids:
                    if not Invoice.objects.filter(customer_id=cid).exists():
                        Customer.objects.filter(pk=cid).delete()

            StockAlert.objects.filter(product_id__in=ids).delete()
            if EmailLog is not None:
                EmailLog.objects.filter(product_id__in=ids).delete()
            StockMovement.objects.filter(product_id__in=ids).delete()
            Product.objects.filter(pk__in=ids).delete()

        self.stdout.write(self.style.SUCCESS("Done."))
