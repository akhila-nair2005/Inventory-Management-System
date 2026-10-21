"""
Seeds StockMS with a realistic electronics-store demo dataset.

    python manage.py seed_data --reset

Everything is generated relative to today's date, so the dashboard and the
forecasting page always have "last 6 months of history + this month so far".
The data is deterministic (fixed random seed): running it twice gives the same shape.
"""
import random
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.utils import timezone

from accounts.models import User
from alerts import signals as alert_signals
from alerts.models import EmailLog, StockAlert
from audit import signals as audit_signals
from audit.models import AuditLog
from billing.models import Customer, Invoice, InvoiceItem
from forecasting.engine import shift_month
from inventory.models import (
    Category, GoodsReceipt, GoodsReceiptItem, Product, PurchaseOrder,
    PurchaseOrderItem, StockMovement, Supplier,
)

DEMO_PASSWORD = 'Stock@12345'

CATEGORIES = [
    ('Smartphones', 'SMARTPHONES', '5G flagship and mid-range smartphones'),
    ('Laptops', 'LAPTOPS', 'Ultrabooks, workstation laptops and notebooks'),
    ('Tablets', 'TABLETS', 'Pro tablets and stylus-compatible slates'),
    ('Televisions', 'TELEVISIONS', '4K OLED, QLED and LED smart televisions'),
    ('Accessories', 'ACCESSORIES', 'Headphones, chargers, mice and peripherals'),
]

SUPPLIERS = {
    'apex': dict(
        name='Apex Tech Distribution Pvt Ltd', contact_person='Rohan Menon',
        phone='+91 80 4110 2200', email='orders@apextechdist.example.com',
        address='45 Electronics City Phase 1, Bengaluru, Karnataka 560100', gst_number='29AABCA1234F1Z5'),
    'nexus': dict(
        name='Nexus Pacific Electronics Wholesale', contact_person='Divya Nair',
        phone='+91 484 401 7788', email='supplychain@nexuspacific.example.com',
        address='Plot 12, Infopark Road, Kakkanad, Kochi, Kerala 682042', gst_number='32AAECN5678K1Z9'),
    'vision': dict(
        name='VisionCore Display & Audio Corp.', contact_person='Arjun Iyer',
        phone='+91 44 4200 3321', email='logistics@visioncore.example.com',
        address='88 Guindy Industrial Estate, Chennai, Tamil Nadu 600032', gst_number='33AAFCV9012M1ZQ'),
}

# key, name, brand, sku, category, supplier, price, cost, final stock, reorder, max, monthly units (6 completed months)
PRODUCTS = [
    ('iphone', 'iPhone 16 Pro 256GB Natural Titanium', 'Apple', 'APL-IP16P-256', 'Smartphones', 'apex', 119900, 104500, 24, 10, 80, [8, 11, 13, 16, 19, 22]),
    ('galaxy', 'Galaxy S25 Ultra 512GB Titanium Gray', 'Samsung', 'SAM-S25U-512', 'Smartphones', 'apex', 129999, 111000, 7, 10, 70, [6, 8, 9, 12, 14, 17]),
    ('macbook', 'MacBook Pro 14-inch M4 Pro 24GB/512GB', 'Apple', 'APL-MBP14-M4', 'Laptops', 'nexus', 199900, 176000, 16, 8, 40, [4, 5, 6, 7, 9, 11]),
    ('thinkpad', 'ThinkPad X1 Carbon Gen 12 Ultra 7', 'Lenovo', 'LEN-X1C-G12', 'Laptops', 'nexus', 164990, 143000, 5, 8, 40, [5, 6, 5, 7, 8, 9]),
    ('ipad', 'iPad Pro 13-inch M4 OLED Wi-Fi 256GB', 'Apple', 'APL-IPDP13-M4', 'Tablets', 'apex', 129900, 112500, 14, 8, 45, [7, 7, 8, 8, 9, 10]),
    ('lgtv', 'OLED evo C4 65-inch 4K Smart TV', 'LG', 'LGE-OLED65-C4', 'Televisions', 'vision', 169990, 138000, 0, 5, 25, [3, 4, 5, 6, 8, 10]),
    ('sonytv', 'Bravia 55-inch 4K Google TV X75', 'Sony', 'SNY-BRV55-X75', 'Televisions', 'vision', 62990, 51500, 11, 6, 30, [6, 5, 6, 5, 6, 5]),
    ('sony', 'WH-1000XM5 Wireless Noise Cancelling Headphones', 'Sony', 'SNY-WH1000XM5', 'Accessories', 'vision', 29990, 21500, 32, 10, 80, [12, 14, 15, 18, 21, 25]),
    ('airpods', 'AirPods Pro (2nd generation) USB-C', 'Apple', 'APL-APP2-USBC', 'Accessories', 'apex', 24900, 19400, 40, 12, 90, [10, 12, 11, 13, 12, 14]),
    ('anker', 'Prime 250W GaN Desktop Charger 6-Port', 'Anker', 'ANK-PRM-250W', 'Accessories', 'nexus', 12999, 8600, 8, 10, 70, [9, 10, 12, 13, 15, 18]),
    # Launched recently: only 2 months of sales, so the forecast page shows "not enough history"
    ('mxmaster', 'MX Master 3S Wireless Mouse', 'Logitech', 'LOG-MXM3S', 'Accessories', 'nexus', 9995, 6900, 20, 8, 50, [0, 0, 0, 0, 5, 7]),
]

CUSTOMERS = [
    ('Anu Thomas', '9847012345', 'anu.thomas@example.com', 'Erattupetta, Kottayam'),
    ('Rahul Krishnan', '9946123456', 'rahul.k@example.com', 'Kakkanad, Kochi'),
    ('Fatima Rahman', '9895234567', 'fatima.rahman@example.com', 'Thrissur'),
    ('Sreejith Nair', '9744345678', 'sreejith.nair@example.com', 'Kozhikode'),
    ('Lakshmi Menon', '9633456789', 'lakshmi.menon@example.com', 'Thiruvananthapuram'),
    ('Bluepeak Software Pvt Ltd', '0484 4012345', 'procurement@bluepeak.example.com', 'Infopark, Kochi'),
    ('Greenfield School', '0481 2567890', 'office@greenfield.example.com', 'Pala, Kottayam'),
    ('Joseph Mathew', '9567567890', 'joseph.m@example.com', 'Muvattupuzha'),
    ('Nisha Varghese', '9496678901', '', 'Alappuzha'),
    ('Hari Prasad', '9388789012', 'hari.p@example.com', 'Palakkad'),
]
BUSINESS_CUSTOMERS = {'Bluepeak Software Pvt Ltd', 'Greenfield School'}

# (supplier, months_ago, day, status, [(product_key, qty_ordered, qty_received, qty_damaged)])
PURCHASE_ORDERS = [
    ('apex', 5, 3, 'RECEIVED', [('iphone', 40, 40, 0), ('galaxy', 30, 30, 0), ('ipad', 20, 20, 0)]),
    ('nexus', 4, 6, 'RECEIVED', [('macbook', 20, 20, 0), ('thinkpad', 20, 20, 0), ('anker', 40, 40, 2)]),
    ('vision', 3, 9, 'RECEIVED', [('sony', 45, 45, 0), ('lgtv', 12, 12, 0), ('sonytv', 15, 15, 0)]),
    ('apex', 2, 5, 'RECEIVED', [('iphone', 35, 35, 0), ('galaxy', 25, 25, 0), ('airpods', 40, 40, 0)]),
    ('nexus', 0, -21, 'PARTIALLY_RECEIVED', [('macbook', 12, 6, 0), ('thinkpad', 15, 5, 0)]),
    ('vision', 0, -5, 'PENDING', [('lgtv', 15, 0, 0), ('sony', 20, 0, 0)]),
    ('apex', 0, -2, 'PENDING', [('galaxy', 30, 0, 0)]),
    ('nexus', 0, -45, 'CANCELLED', [('anker', 30, 0, 0)]),
]


@contextmanager
def signals_paused():
    """Seed rows must not fire stock-alert e-mails or one audit entry per row."""
    pairs = [
        (post_save, alert_signals.check_low_stock, Product),
        (post_save, audit_signals.log_product_save, Product),
        (post_delete, audit_signals.log_product_delete, Product),
        (post_save, audit_signals.log_invoice_save, Invoice),
        (post_delete, audit_signals.log_invoice_delete, Invoice),
    ]
    for signal, receiver, sender in pairs:
        signal.disconnect(receiver, sender=sender)
    try:
        yield
    finally:
        for signal, receiver, sender in pairs:
            signal.connect(receiver, sender=sender)


def aware(dt):
    return dt if timezone.is_aware(dt) else dt.replace(tzinfo=dt_timezone.utc)


def set_dates(model, rows, field):
    """auto_now_add ignores supplied values, so back-date rows with an UPDATE afterwards."""
    for obj, when in rows:
        model.objects.filter(pk=obj.pk).update(**{field: when})


class Command(BaseCommand):
    help = 'Seeds the database with a realistic electronics inventory & sales demo dataset.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Delete all products, suppliers, invoices, purchase orders, alerts, e-mail and audit logs first '
                 '(user accounts are kept).',
        )

    # ------------------------------------------------------------------ entry point
    def handle(self, *args, **options):
        has_data = Product.objects.exists() or Invoice.objects.exists()
        if has_data and not options['reset']:
            raise CommandError(
                "The database already has products or invoices. Run "
                "'python manage.py seed_data --reset' to replace them with the demo dataset "
                "(user accounts are kept)."
            )

        self.rng = random.Random(2026)
        self.now = timezone.now()
        self.pending_emails = []

        with signals_paused(), transaction.atomic():
            if options['reset']:
                self.stdout.write('Clearing existing business data...')
                self.wipe()

            users = self.seed_users()
            categories = self.seed_categories()
            suppliers = self.seed_suppliers()
            products = self.seed_products(categories, suppliers)
            customers = self.seed_customers()

            ledger = []     # (product_key, 'IN'/'OUT', qty, datetime, note, user)
            self.seed_purchase_orders(products, suppliers, users, ledger)
            invoice_count = self.seed_invoices(products, customers, users, ledger)
            self.seed_stock_ledger(products, users, ledger)
            self.seed_alerts_and_emails(products, suppliers, users)
            self.seed_audit_logs(products, users)

        self.report(invoice_count)

    # ------------------------------------------------------------------ wipe
    def wipe(self):
        InvoiceItem.objects.all().delete()
        Invoice.objects.all().delete()
        Customer.objects.all().delete()
        GoodsReceiptItem.objects.all().delete()
        GoodsReceipt.objects.all().delete()
        PurchaseOrderItem.objects.all().delete()
        PurchaseOrder.objects.all().delete()
        StockAlert.objects.all().delete()
        EmailLog.objects.all().delete()
        StockMovement.objects.all().delete()
        Product.objects.all().delete()
        Supplier.objects.all().delete()
        Category.objects.all().delete()
        AuditLog.objects.all().delete()

    # ------------------------------------------------------------------ users
    def seed_users(self):
        def ensure(username, role, first, last, email, phone, department, active=True, superuser=False):
            user = User.objects.filter(username=username).first()
            if user is None:
                user = User(username=username, role=role, first_name=first, last_name=last,
                            is_active=active, is_staff=(role == 'ADMIN'), is_superuser=superuser)
                user.set_password(DEMO_PASSWORD)
            # Fill blanks only; never overwrite what the user has already set
            user.email = user.email or email
            user.phone = user.phone or phone
            user.department = user.department or department
            user.first_name = user.first_name or first
            user.last_name = user.last_name or last
            user.save()
            return user

        users = {
            'admin': ensure('admin', 'ADMIN', 'System', 'Administrator', 'admin@stockms.example.com',
                            '9000000001', 'Administration', superuser=True),
            'manager': ensure('Manager', 'MANAGER', 'Priya', 'Sharma', 'manager@stockms.example.com',
                              '9000000002', 'Purchasing'),
            'staff': ensure('Staff', 'STAFF', 'Rahul', 'Das', 'staff@stockms.example.com',
                            '9000000003', 'Billing Counter'),
        }
        users['staff2'] = ensure('meera', 'STAFF', 'Meera', 'Pillai', 'meera@stockms.example.com',
                                 '9000000004', 'Warehouse')
        users['manager2'] = ensure('arun', 'MANAGER', 'Arun', 'Kumar', 'arun@stockms.example.com',
                                   '9000000005', 'Sales')
        ensure('joseph', 'STAFF', 'Joseph', 'George', 'joseph@stockms.example.com',
               '9000000006', 'Warehouse', active=False)   # inactive account, to show status in Staff Management
        return users

    # ------------------------------------------------------------------ catalogue
    def seed_categories(self):
        return {
            name: Category.objects.create(name=name, code=code, description=desc)
            for name, code, desc in CATEGORIES
        }

    def seed_suppliers(self):
        return {key: Supplier.objects.create(**data) for key, data in SUPPLIERS.items()}

    def seed_products(self, categories, suppliers):
        products = {}
        for key, name, brand, sku, cat, sup, price, cost, stock, reorder, maximum, curve in PRODUCTS:
            product = Product.objects.create(
                name=name, brand=brand, sku=sku,
                barcode=f"890{len(products) + 1:09d}",
                category=categories[cat], supplier=suppliers[sup],
                price=Decimal(price), cost_price=Decimal(cost),
                quantity=0, reorder_level=reorder, max_stock_level=maximum,
            )
            product._target_stock = stock
            product._curve = curve
            products[key] = product
        return products

    def seed_customers(self):
        return [Customer.objects.create(name=n, phone=p, email=e, address=a) for n, p, e, a in CUSTOMERS]

    # ------------------------------------------------------------------ purchasing
    def month_date(self, months_ago, day, hour=11):
        year, month = shift_month(self.now.year, self.now.month, -months_ago)
        return aware(datetime(year, month, min(day, 28), hour, self.rng.randint(0, 59)))

    def seed_purchase_orders(self, products, suppliers, users, ledger):
        manager = users['manager']
        for seq, (sup_key, months_ago, day, status, lines) in enumerate(PURCHASE_ORDERS, start=1):
            if day < 0:        # negative day = "this many days ago"
                order_dt = self.now - timedelta(days=-day, hours=self.rng.randint(0, 5))
            else:
                order_dt = self.month_date(months_ago, day)

            order = PurchaseOrder.objects.create(
                order_number=f"PO-{order_dt.year}-{100 + seq}",
                supplier=suppliers[sup_key], created_by=manager, status=status,
                expected_delivery_date=(order_dt + timedelta(days=7)).date(),
                payment_terms='Net 15 days', delivery_address='Main Warehouse, Kochi',
                tax_percent=Decimal('18'), discount_amount=Decimal('0'),
                notes='Auto-generated demo purchase order',
            )
            set_dates(PurchaseOrder, [(order, order_dt)], 'order_date')
            if status == 'PENDING':
                PurchaseOrder.objects.filter(pk=order.pk).update(
                    confirmed_delivery_date=(self.now + timedelta(days=3)).date())

            items = []
            for key, ordered, received, damaged in lines:
                product = products[key]
                item = PurchaseOrderItem.objects.create(
                    purchase_order=order, product=product,
                    quantity_ordered=ordered, unit_cost=product.cost_price,
                )
                items.append((item, received, damaged))

            if status in ('RECEIVED', 'PARTIALLY_RECEIVED'):
                receipt_dt = order_dt + timedelta(days=4 if status == 'RECEIVED' else 3)
                receipt = GoodsReceipt.objects.create(
                    purchase_order=order, received_by=manager,
                    remarks='Delivery checked and counted at the warehouse.'
                            + (' Some units arrived damaged.' if any(d for _, _, d in items) else ''),
                )
                set_dates(GoodsReceipt, [(receipt, receipt_dt)], 'received_date')
                for item, received, damaged in items:
                    if received:
                        GoodsReceiptItem.objects.create(
                            receipt=receipt, po_item=item,
                            quantity_received=received, quantity_damaged=damaged)
                        usable = received - damaged
                        if usable > 0:
                            ledger.append((item.product, 'IN', usable, receipt_dt,
                                           f"Received from {order.order_number} (Receipt #{receipt.pk})", manager))

            # purchase-order e-mail to the supplier, plus a discrepancy notice when goods were damaged
            self.pending_emails.append(('PO', order, order_dt))
            if any(d for _, _, d in items):
                self.pending_emails.append(('DISCREPANCY', order, order_dt + timedelta(days=4)))

    # ------------------------------------------------------------------ sales
    def seed_invoices(self, products, customers, users, ledger):
        rng = self.rng
        sellers = [users['staff'], users['staff2'], users['manager'], users['manager2'], users['admin']]
        today = self.now

        # Units per product per month: 6 completed months + the current month so far
        months = [shift_month(today.year, today.month, -i) for i in range(6, 0, -1)]
        months.append((today.year, today.month))
        days_in_month = lambda y, m: (datetime(*shift_month(y, m, 1), 1) - datetime(y, m, 1)).days

        invoices_made = 0
        all_invoices = []   # (datetime, lines[(product, qty)], customer, payment, status)

        for idx, (year, month) in enumerate(months):
            current = (idx == len(months) - 1)
            last_day = today.day if current else days_in_month(year, month)

            lines = []
            for product in products.values():
                if current:
                    base = product._curve[-1]
                    units = round(base * today.day / days_in_month(year, month) * 1.1) if base else 0
                    units = max(units, 1) if base and today.day >= 3 else units
                else:
                    units = product._curve[idx]
                remaining = units
                while remaining > 0:
                    chunk = min(remaining, rng.choice([1, 1, 1, 2, 2, 3]))
                    lines.append((rng.randint(1, last_day), product, chunk))
                    remaining -= chunk

            lines.sort(key=lambda l: l[0])
            # bundle neighbouring lines (same month) into invoices of 1-3 items
            i = 0
            while i < len(lines):
                size = rng.choice([1, 1, 2, 2, 3])
                group = lines[i:i + size]
                i += size
                day = group[0][0]
                hour, minute = rng.randint(10, 19), rng.randint(0, 59)
                when = aware(datetime(year, month, day, hour, minute))
                if when > self.now:
                    # never cross into the previous month, or the history curve would shift
                    when = max(self.now - timedelta(minutes=rng.randint(1, 40)),
                               aware(datetime(year, month, 1, 0, 1)))
                merged = {}
                for _, product, qty in group:
                    merged[product.pk] = (product, merged.get(product.pk, (product, 0))[1] + qty)
                all_invoices.append((when, list(merged.values())))

        # Two cancelled invoices (stock was returned), kept out of the forecast curves
        for months_ago, key, qty in [(2, 'sony', 2), (1, 'airpods', 1)]:
            y, m = shift_month(today.year, today.month, -months_ago)
            when = aware(datetime(y, m, 18, 15, 20))
            all_invoices.append((when, [(products[key], qty)], 'CANCELLED'))

        all_invoices.sort(key=lambda row: row[0])
        counters = {}
        for row in all_invoices:
            when, line_items = row[0], row[1]
            cancelled = len(row) == 3

            customer = None if rng.random() < 0.35 else rng.choice(customers)
            payment = rng.choices(['CASH', 'CARD', 'UPI', 'CREDIT'], weights=[25, 30, 35, 10])[0]
            seller = rng.choice(sellers)

            subtotal = sum(p.price * q for p, q in line_items)
            discount = Decimal('0')
            if customer and customer.name in BUSINESS_CUSTOMERS:
                discount = (subtotal * Decimal('0.02')).quantize(Decimal('1'))
                payment = 'CREDIT' if rng.random() < 0.5 else 'CARD'

            age_days = (self.now - when).days
            if cancelled:
                status = 'CANCELLED'
            elif payment == 'CREDIT' and age_days < 20:
                status = 'PENDING'
            elif age_days < 2 and rng.random() < 0.4:
                status = 'PENDING'
            else:
                status = 'PAID'

            key = (when.year, when.month)
            counters[key] = counters.get(key, 0) + 1
            invoice = Invoice.objects.create(
                invoice_number=f"INV-{when:%y%m}-{counters[key]:04d}",
                customer=customer, created_by=seller, status=status,
                payment_method=payment, tax_percent=Decimal('18'), discount_amount=discount,
            )
            set_dates(Invoice, [(invoice, when)], 'created_at')

            for product, qty in line_items:
                InvoiceItem.objects.create(
                    invoice=invoice, product=product, quantity=qty,
                    unit_price=product.price, unit_cost=product.cost_price,
                )
                ledger.append((product, 'OUT', qty, when, f"Sold via {invoice.invoice_number}", seller))
                if cancelled:
                    back = when + timedelta(hours=3)
                    ledger.append((product, 'IN', qty, back,
                                   f"Returned: {invoice.invoice_number} cancelled", users['manager']))
            invoices_made += 1
            self.last_invoice = invoice
        return invoices_made

    # ------------------------------------------------------------------ stock ledger
    def seed_stock_ledger(self, products, users, ledger):
        """
        Writes the stock-movement history and sets each product's quantity to its
        planned final level. The opening balance is derived so that
        opening + all IN - all OUT == final stock, which keeps the ledger consistent.
        """
        start = self.month_date(7, 1, hour=9)
        by_product = {}
        for product, kind, qty, when, note, user in ledger:
            by_product.setdefault(product.pk, []).append((kind, qty))

        rows = []
        for product in products.values():
            moves = by_product.get(product.pk, [])
            total_in = sum(q for k, q in moves if k == 'IN')
            total_out = sum(q for k, q in moves if k == 'OUT')
            opening = max(product._target_stock + total_out - total_in, 0)
            if opening:
                ledger.append((product, 'IN', opening, start, 'Opening stock balance', users['admin']))

        ledger.sort(key=lambda row: row[3])
        for product, kind, qty, when, note, user in ledger:
            movement = StockMovement(product=product, movement_type=kind, quantity=qty,
                                     performed_by=user, note=note)
            rows.append((movement, when))

        # bulk_create skips StockMovement.save(), so quantities are set explicitly below
        StockMovement.objects.bulk_create([m for m, _ in rows])
        saved = list(StockMovement.objects.order_by('-pk')[:len(rows)])[::-1]
        set_dates(StockMovement, [(obj, when) for obj, (_, when) in zip(saved, rows)], 'timestamp')

        for product in products.values():
            Product.objects.filter(pk=product.pk).update(quantity=product._target_stock)
            product.quantity = product._target_stock

    # ------------------------------------------------------------------ alerts + e-mail log
    def seed_alerts_and_emails(self, products, suppliers, users):
        recipients = list(
            User.objects.filter(role__in=['ADMIN', 'MANAGER', 'STAFF'], is_active=True)
            .exclude(email='').values_list('email', flat=True))
        manager_emails = list(
            User.objects.filter(role__in=['ADMIN', 'MANAGER'], is_active=True)
            .exclude(email='').values_list('email', flat=True))

        email_rows = []

        def add_email(when, kind, subject, body, to, product=None, user=None, status='SENT'):
            for address in to:
                email_rows.append((EmailLog(
                    recipient_email=address, subject=subject, body=body, alert_type=kind,
                    status=status, product=product, triggered_by=user), when))

        # active alerts for products that are currently low / out of stock
        for product in products.values():
            if not product.is_low_stock:
                continue
            kind = 'OUT_OF_STOCK' if product.quantity == 0 else 'LOW_STOCK'
            when = self.now - timedelta(days=self.rng.randint(1, 4), hours=self.rng.randint(0, 6))
            alert = StockAlert.objects.create(
                product=product, alert_type=kind,
                quantity_at_alert=product.quantity, reorder_level_at_alert=product.reorder_level)
            set_dates(StockAlert, [(alert, when)], 'created_at')

            if kind == 'OUT_OF_STOCK':
                subject = f"[OUT OF STOCK] {product.name} ({product.sku})"
                body = (f"Product '{product.name}' (SKU: {product.sku}) has reached 0 units.\n"
                        f"Supplier: {product.supplier.name}\n"
                        f"Suggested reorder quantity: {product.suggested_reorder_quantity}\n\n"
                        f"Immediate purchase order recommended.")
            else:
                subject = f"[LOW STOCK] {product.name} ({product.quantity} units left)"
                body = (f"Product '{product.name}' (SKU: {product.sku}) has dropped to {product.quantity} units, "
                        f"at or below its reorder level of {product.reorder_level} units.\n"
                        f"Supplier: {product.supplier.name}\n"
                        f"Suggested reorder quantity: {product.suggested_reorder_quantity}\n\n"
                        f"Please arrange a restock soon.")
            add_email(when, kind, subject, body, recipients, product)

        # a few historic alerts that were resolved after restocking
        for key, days_ago, resolved_after in [('iphone', 70, 5), ('sony', 45, 4), ('galaxy', 30, 6)]:
            product = products[key]
            created = self.now - timedelta(days=days_ago)
            alert = StockAlert.objects.create(
                product=product, alert_type='LOW_STOCK', quantity_at_alert=product.reorder_level - 1,
                reorder_level_at_alert=product.reorder_level, resolved=True,
                resolved_at=created + timedelta(days=resolved_after))
            set_dates(StockAlert, [(alert, created)], 'created_at')
            add_email(created, 'LOW_STOCK', f"[LOW STOCK] {product.name} ({product.reorder_level - 1} units left)",
                      f"Product '{product.name}' dropped below its reorder level.", recipients, product)

        # purchase-order confirmations and discrepancy notices queued by seed_purchase_orders
        for kind, order, when in self.pending_emails:
            supplier = order.supplier
            if kind == 'PO':
                lines = "\n".join(f"- {i.product.name}: {i.quantity_ordered} units @ \u20b9{i.unit_cost} each"
                                  for i in order.items.all())
                add_email(when, 'PURCHASE_CONFIRMATION', f"New Purchase Order: {order.order_number}",
                          f"Dear {supplier.contact_person},\n\nWe would like to place the following order:\n\n"
                          f"{lines}\n\nGrand Total: \u20b9{order.grand_total}\n\nRegards,\nStockMS",
                          [supplier.email], user=users['manager'])
            else:
                add_email(when, 'DELIVERY_DISCREPANCY', f"Discrepancy in Delivery for {order.order_number}",
                          f"Dear {supplier.contact_person},\n\nSome units in order {order.order_number} "
                          f"arrived damaged. Please advise on replacement or credit.\n\nRegards,\nStockMS",
                          [supplier.email], user=users['manager'])
        self.pending_emails = []

        add_email(self.now - timedelta(days=6), 'FORECAST_REPORT', '[FORECAST REPORT] 4 product(s) need restocking',
                  'Demand forecast report. Open Forecasting in StockMS for the full table.',
                  manager_emails, user=users['admin'])
        customer_invoice = Invoice.objects.filter(customer__email__gt='').order_by('-created_at').first()
        if customer_invoice:
            add_email(customer_invoice.created_at, 'INVOICE', f"Your invoice {customer_invoice.invoice_number}",
                      f"Dear {customer_invoice.customer.name},\n\nYour invoice is attached.\n\nRegards,\nStockMS",
                      [customer_invoice.customer.email], user=users['staff'])

        EmailLog.objects.bulk_create([row for row, _ in email_rows])
        saved = list(EmailLog.objects.order_by('-pk')[:len(email_rows)])[::-1]
        set_dates(EmailLog, [(obj, when) for obj, (_, when) in zip(saved, email_rows)], 'created_at')

    # ------------------------------------------------------------------ audit trail
    def seed_audit_logs(self, products, users):
        entries = []
        opening = self.month_date(7, 1, hour=9)
        for product in products.values():
            entries.append((AuditLog(user=users['admin'], action='CREATE', model_name='Product',
                                     object_id=str(product.pk), object_repr=str(product)), opening))
        for key, days_ago in [('iphone', 40), ('galaxy', 25), ('anker', 18)]:
            product = products[key]
            entries.append((AuditLog(user=users['manager'], action='UPDATE', model_name='Product',
                                     object_id=str(product.pk), object_repr=str(product)),
                            self.now - timedelta(days=days_ago)))
        for invoice in Invoice.objects.order_by('-created_at')[:25]:
            entries.append((AuditLog(user=invoice.created_by, action='CREATE', model_name='Invoice',
                                     object_id=str(invoice.pk), object_repr=str(invoice)), invoice.created_at))

        AuditLog.objects.bulk_create([row for row, _ in entries])
        saved = list(AuditLog.objects.order_by('-pk')[:len(entries)])[::-1]
        set_dates(AuditLog, [(obj, when) for obj, (_, when) in zip(saved, entries)], 'timestamp')

    # ------------------------------------------------------------------ summary
    def report(self, invoice_count):
        self.stdout.write(self.style.SUCCESS('\nDemo data created.'))
        self.stdout.write(f"  Categories: {Category.objects.count()}   Suppliers: {Supplier.objects.count()}   "
                          f"Products: {Product.objects.count()}   Customers: {Customer.objects.count()}")
        self.stdout.write(f"  Invoices: {invoice_count}   Purchase orders: {PurchaseOrder.objects.count()}   "
                          f"Stock movements: {StockMovement.objects.count()}")
        self.stdout.write(f"  Active stock alerts: {StockAlert.objects.filter(resolved=False).count()}   "
                          f"E-mail log rows: {EmailLog.objects.count()}")
        self.stdout.write('\n  Accounts (password for accounts created now: ' + DEMO_PASSWORD + '):')
        for user in User.objects.order_by('role', 'username'):
            self.stdout.write(f"    {user.username:<10} {user.role:<8} {'active' if user.is_active else 'inactive'}")
        self.stdout.write('  (Existing accounts keep their current passwords.)')
