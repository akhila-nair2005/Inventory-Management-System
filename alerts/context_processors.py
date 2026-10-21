from .models import StockAlert


def alert_counts(request):
    """Adds the number of active stock alerts so the navbar can show a badge."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    return {'active_alert_count': StockAlert.objects.filter(resolved=False).count()}
