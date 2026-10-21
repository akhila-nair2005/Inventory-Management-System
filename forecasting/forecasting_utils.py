"""
Database layer for demand forecasting.

History = units sold per calendar month, taken from invoice items (cancelled
invoices are ignored). The six most recent COMPLETED months are used, because
the current month is still in progress and would drag the trend down. The
forecast covers the current month and the two after it.
"""
from datetime import datetime

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from billing.models import InvoiceItem
from inventory.models import Product
from . import engine

HISTORY_MONTHS = 6
HORIZON_MONTHS = 3


def get_periods(today=None):
    """Return (history, future) as lists of (year, month, label)."""
    today = today or timezone.now()
    y, m = today.year, today.month
    history = [engine.shift_month(y, m, -i) for i in range(HISTORY_MONTHS, 0, -1)]
    future = [engine.shift_month(y, m, i) for i in range(0, HORIZON_MONTHS)]
    to_tuple = lambda ym: (ym[0], ym[1], engine.month_label(*ym))
    return [to_tuple(p) for p in history], [to_tuple(p) for p in future]


def monthly_units_by_product(history_periods, product_ids=None):
    """{product_id: {(year, month): units}} for the history window, in one query."""
    first_year, first_month, _ = history_periods[0]
    last_year, last_month, _ = history_periods[-1]
    end_year, end_month = engine.shift_month(last_year, last_month, 1)

    tz = timezone.get_current_timezone()
    start = datetime(first_year, first_month, 1, tzinfo=tz)
    end = datetime(end_year, end_month, 1, tzinfo=tz)

    qs = InvoiceItem.objects.filter(
        invoice__created_at__gte=start,
        invoice__created_at__lt=end,
    ).exclude(invoice__status='CANCELLED')
    if product_ids is not None:
        qs = qs.filter(product_id__in=product_ids)

    rows = (
        qs.annotate(month=TruncMonth('invoice__created_at'))
        .values('product_id', 'month')
        .annotate(units=Sum('quantity'))
    )

    data = {}
    for row in rows:
        month = row['month']
        data.setdefault(row['product_id'], {})[(month.year, month.month)] = row['units']
    return data


def _build_product_forecast(product, monthly, history_periods, future_periods, window):
    history_values = [monthly.get((y, m), 0) for y, m, _ in history_periods]
    model = engine.forecast_series(history_values, horizon=len(future_periods), window=window)

    on_order = product.quantity_on_order
    restock = 0
    months_of_cover = None
    if model['status'] == 'OK':
        restock = engine.recommended_restock(
            model['blended_next_month'], product.quantity, on_order, product.reorder_level
        )
        if model['blended_next_month'] > 0:
            months_of_cover = round(product.quantity / model['blended_next_month'], 1)

    return {
        'product_id': product.id,
        'name': product.name,
        'sku': product.sku,
        'brand': product.brand,
        'category': product.category.name if product.category else '-',
        'current_stock': product.quantity,
        'on_order': on_order,
        'reorder_level': product.reorder_level,
        'unit_price': float(product.price),
        'history_labels': [label for _, _, label in history_periods],
        'history_values': history_values,
        'future_labels': [label for _, _, label in future_periods],
        'recommended_restock': restock,
        'months_of_cover': months_of_cover,
        'stockout_risk': (
            model['status'] == 'OK' and product.quantity < model['blended_next_month']
        ),
        'window': window,
        **model,
    }


def get_all_forecasts(window=3, today=None):
    """Forecast every product (one database query for all the sales history)."""
    history_periods, future_periods = get_periods(today)
    products = list(Product.objects.select_related('category').all())
    sales = monthly_units_by_product(history_periods, [p.id for p in products])
    forecasts = [
        _build_product_forecast(p, sales.get(p.id, {}), history_periods, future_periods, window)
        for p in products
    ]
    return forecasts


def get_product_forecast(product, window=3, today=None):
    history_periods, future_periods = get_periods(today)
    sales = monthly_units_by_product(history_periods, [product.id])
    return _build_product_forecast(
        product, sales.get(product.id, {}), history_periods, future_periods, window
    )


PRIORITY_ORDER = {'HIGH_DEMAND': 0, 'MODERATE_DEMAND': 1, 'LOW_DEMAND': 2}


def sort_by_urgency(forecasts):
    """Largest restock need first, then highest demand."""
    return sorted(
        forecasts,
        key=lambda f: (-f['recommended_restock'], PRIORITY_ORDER[f['priority']], f['name']),
    )
