from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import StockAlert


@login_required
def alert_list(request):
    alerts = StockAlert.objects.select_related('product').filter(resolved=False)
    resolved_alerts = StockAlert.objects.select_related('product').filter(resolved=True)[:10]
    return render(request, 'alerts/alert_list.html', {
        'alerts': alerts,
        'resolved_alerts': resolved_alerts,
    })


@login_required
def resolve_alert(request, pk):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "You don't have permission to resolve alerts.")
        return redirect('alert_list')

    alert = get_object_or_404(StockAlert, pk=pk)
    alert.resolved = True
    from django.utils import timezone
    alert.resolved_at = timezone.now()
    alert.save()
    messages.success(request, f"Alert for {alert.product.name} marked as resolved.")
    return redirect('alert_list')