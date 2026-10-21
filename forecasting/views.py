from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from alerts.models import EmailLog
from alerts.services import dispatch_email, get_alert_recipients
from inventory.models import Product
from .forecasting_utils import (
    get_all_forecasts, get_product_forecast, sort_by_urgency,
)


def _window_from_request(request, default=3):
    try:
        window = int(request.GET.get('window', default))
    except (TypeError, ValueError):
        return default
    return window if 2 <= window <= 4 else default


@login_required
def forecast_view(request, product_id):
    """JSON API: monthly forecast for one product."""
    product = get_object_or_404(Product, id=product_id)
    return JsonResponse(get_product_forecast(product, window=_window_from_request(request)))


@login_required
def forecast_page(request):
    window = _window_from_request(request)
    forecasts = sort_by_urgency(get_all_forecasts(window=window))
    by_id = {f['product_id']: f for f in forecasts}

    # Selected product: ?product=<id>, otherwise the one that needs attention first
    selected = None
    product_id = request.GET.get('product')
    if product_id and product_id.isdigit():
        selected = by_id.get(int(product_id))
    if selected is None:
        selected = next((f for f in forecasts if f['status'] == 'OK'), forecasts[0] if forecasts else None)

    ok = [f for f in forecasts if f['status'] == 'OK']
    cost_by_id = dict(Product.objects.values_list('id', 'cost_price'))
    restock_cost = sum(
        Decimal(f['recommended_restock']) * (cost_by_id.get(f['product_id']) or 0) for f in ok
    )

    chart_rows = sorted(ok, key=lambda f: -f['blended_next_month'])[:8]
    context = {
        'forecasts': forecasts,
        'selected': selected,
        'window': window,
        'products_to_restock': sum(1 for f in ok if f['recommended_restock'] > 0),
        'high_demand_count': sum(1 for f in ok if f['priority'] == 'HIGH_DEMAND'),
        'stockout_risk_count': sum(1 for f in ok if f['stockout_risk']),
        'restock_cost': restock_cost,
        'insufficient_count': len(forecasts) - len(ok),
        'can_email': request.user.role in ('ADMIN', 'MANAGER'),
        'chart_data': {
            'selected': selected,
            'compare': {
                'labels': [f['sku'] for f in chart_rows],
                'stock': [f['current_stock'] for f in chart_rows],
                'demand': [f['blended_next_month'] for f in chart_rows],
                'restock': [f['recommended_restock'] for f in chart_rows],
            },
        },
    }
    return render(request, 'forecasting/forecast_page.html', context)


@login_required
def email_forecast_report(request):
    """Email the restock recommendations to Admins and Managers (logged in the email console)."""
    if request.user.role not in ('ADMIN', 'MANAGER'):
        messages.error(request, "You don't have permission to send forecast reports.")
        return redirect('forecast_page')
    if request.method != 'POST':
        return redirect('forecast_page')

    forecasts = [f for f in sort_by_urgency(get_all_forecasts()) if f['status'] == 'OK']
    needing = [f for f in forecasts if f['recommended_restock'] > 0]

    lines = [
        f"Demand forecast report - {timezone.now():%d %b %Y}",
        f"Next-month forecast = average of Linear Regression and Moving Average.",
        "",
    ]
    if needing:
        lines.append("Recommended restock:")
        for f in needing:
            lines.append(
                f"- {f['name']} ({f['sku']}): stock {f['current_stock']}, "
                f"on order {f['on_order']}, forecast {f['blended_next_month']}/month "
                f"-> order {f['recommended_restock']} units"
            )
    else:
        lines.append("All products have enough stock for the forecast demand.")
    lines += ["", "Regards,", "StockMS"]

    recipients = get_alert_recipients(roles=('ADMIN', 'MANAGER'))
    sent = dispatch_email(
        subject=f"[FORECAST REPORT] {len(needing)} product(s) need restocking",
        body="\n".join(lines),
        recipients=recipients,
        alert_type=EmailLog.AlertType.FORECAST_REPORT,
        triggered_by=request.user,
    )
    if not recipients:
        messages.warning(request, "No Admin/Manager has an e-mail address on file, so nothing was sent.")
    elif sent:
        messages.success(request, f"Forecast report sent to {len(recipients)} recipient(s).")
    else:
        messages.error(request, "The e-mail could not be sent. Check the Email Log for details.")
    return redirect('forecast_page')
