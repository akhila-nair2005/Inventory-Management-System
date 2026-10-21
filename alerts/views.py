from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import StockAlert, EmailLog


@login_required
def alert_list(request):
    alerts = StockAlert.objects.select_related('product', 'product__supplier').filter(resolved=False)
    resolved_alerts = StockAlert.objects.select_related('product').filter(
        resolved=True
    ).order_by('-resolved_at')[:10]

    return render(request, 'alerts/alert_list.html', {
        'alerts': alerts,
        'resolved_alerts': resolved_alerts,
        'out_count': alerts.filter(alert_type=StockAlert.AlertType.OUT_OF_STOCK).count(),
        'low_count': alerts.filter(alert_type=StockAlert.AlertType.LOW_STOCK).count(),
    })


@login_required
def resolve_alert(request, pk):
    # Only Admin and Manager can resolve alerts
    if request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "You don't have permission to resolve alerts.")
        return redirect('alert_list')

    alert = get_object_or_404(StockAlert, pk=pk)
    product = alert.product

    # The alert can only be closed once stock is back above the reorder level
    if product.is_low_stock:
        messages.error(
            request,
            f"{product.name} is still at or below the reorder level. "
            f"Current stock: {product.quantity}, Reorder level: {product.reorder_level}."
        )
        return redirect('alert_list')

    alert.resolved = True
    alert.resolved_at = timezone.now()
    alert.save()
    messages.success(request, f"Alert for {product.name} marked as resolved.")
    return redirect('alert_list')


@login_required
def email_log_list(request):
    """The SMTP 'email console': every message the system has sent."""
    if request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "You don't have permission to view the email log.")
        return redirect('dashboard')

    logs = EmailLog.objects.select_related('product')
    type_filter = request.GET.get('type', '')
    if type_filter:
        logs = logs.filter(alert_type=type_filter)

    return render(request, 'alerts/email_log_list.html', {
        'logs': logs[:200],
        'type_filter': type_filter,
        'type_choices': EmailLog.AlertType.choices,
        'total_sent': EmailLog.objects.filter(status='SENT').count(),
        'total_failed': EmailLog.objects.filter(status='FAILED').count(),
    })
