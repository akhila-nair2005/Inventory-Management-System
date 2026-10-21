"""Sales / procurement aggregates shared by the dashboard and the reports page."""
from datetime import datetime
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from billing.models import Invoice, InvoiceItem

MONEY = DecimalField(max_digits=16, decimal_places=2)
ZERO = Decimal('0.00')


def shift_month(year, month, offset):
    index = year * 12 + (month - 1) + offset
    return index // 12, index % 12 + 1


def month_start(year, month):
    return datetime(year, month, 1, tzinfo=timezone.get_current_timezone())


def valid_invoices():
    """Invoices that count as sales (everything except cancelled ones)."""
    return Invoice.objects.exclude(status='CANCELLED')


def monthly_sales(months=6, today=None):
    """
    Revenue, profit, and units for the last `months` months INCLUDING the current one.
    Returns a list of dicts oldest -> newest.
    """
    today = today or timezone.now()
    periods = [shift_month(today.year, today.month, -i) for i in range(months - 1, -1, -1)]
    start = month_start(*periods[0])

    rows = {p: {'revenue': ZERO, 'profit': ZERO, 'units': 0, 'invoices': 0} for p in periods}
    invoices = valid_invoices().filter(created_at__gte=start).prefetch_related('items')
    for inv in invoices:
        key = (inv.created_at.year, inv.created_at.month)
        if key not in rows:
            continue
        rows[key]['revenue'] += inv.total_amount
        rows[key]['profit'] += inv.gross_profit
        rows[key]['units'] += sum(i.quantity for i in inv.items.all())
        rows[key]['invoices'] += 1

    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    return [
        {'label': f"{month_names[m - 1]} {y}", **rows[(y, m)]}
        for (y, m) in periods
    ]


def sales_totals(today=None):
    """All-time revenue, this-month and today figures."""
    today = today or timezone.now()
    month_begin = month_start(today.year, today.month)

    all_time = ZERO
    this_month = ZERO
    month_profit = ZERO
    todays = ZERO
    count = 0
    for inv in valid_invoices().prefetch_related('items'):
        total = inv.total_amount
        all_time += total
        count += 1
        if inv.created_at >= month_begin:
            this_month += total
            month_profit += inv.gross_profit
        if inv.created_at.date() == today.date():
            todays += total
    return {
        'all_time': all_time,
        'this_month': this_month,
        'month_profit': month_profit,
        'today': todays,
        'invoice_count': count,
    }


def top_products(limit=5):
    return list(
        InvoiceItem.objects.exclude(invoice__status='CANCELLED')
        .values('product__name', 'product__sku')
        .annotate(
            units=Sum('quantity'),
            revenue=Sum(ExpressionWrapper(F('quantity') * F('unit_price'), output_field=MONEY)),
        )
        .order_by('-units')[:limit]
    )


def sales_by_category():
    return list(
        InvoiceItem.objects.exclude(invoice__status='CANCELLED')
        .values('product__category__name')
        .annotate(
            units=Sum('quantity'),
            revenue=Sum(ExpressionWrapper(F('quantity') * F('unit_price'), output_field=MONEY)),
        )
        .order_by('-revenue')
    )


def sales_by_payment_method():
    rows = {}
    for inv in valid_invoices().prefetch_related('items'):
        label = inv.get_payment_method_display()
        rows[label] = rows.get(label, ZERO) + inv.total_amount
    return sorted(rows.items(), key=lambda kv: -kv[1])


def procurement_spend():
    """Money spent on goods actually received (quantity received x PO unit cost)."""
    from inventory.models import GoodsReceiptItem
    total = GoodsReceiptItem.objects.aggregate(
        t=Sum(ExpressionWrapper(F('quantity_received') * F('po_item__unit_cost'), output_field=MONEY))
    )['t']
    return total or ZERO
