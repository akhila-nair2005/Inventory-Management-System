from django.contrib import admin

from accounts.permissions import RoleRestrictedAdminMixin
from .models import StockAlert, EmailLog


# read-only, system-generated
@admin.register(StockAlert)
class StockAlertAdmin(RoleRestrictedAdminMixin, admin.ModelAdmin):
    list_display = ['product', 'alert_type', 'quantity_at_alert', 'reorder_level_at_alert', 'resolved', 'created_at']
    list_filter = ['alert_type', 'resolved', 'created_at']
    allowed_roles_add = []                       # Nobody manually creates alerts, only the signal does
    allowed_roles_change = ['ADMIN', 'MANAGER']  # Manager marks alerts as resolved once restocked
    allowed_roles_delete = ['ADMIN']

    def has_add_permission(self, request):
        return False  # Alerts are system-generated only, never manual


@admin.register(EmailLog)
class EmailLogAdmin(RoleRestrictedAdminMixin, admin.ModelAdmin):
    """Audit trail of sent e-mail: viewable, never hand-edited."""
    list_display = ['created_at', 'alert_type', 'recipient_email', 'subject', 'status']
    list_filter = ['alert_type', 'status']
    search_fields = ['subject', 'recipient_email']
    allowed_roles_view = ['ADMIN', 'MANAGER']
    allowed_roles_add = []
    allowed_roles_change = []
    allowed_roles_delete = ['ADMIN']

    def has_add_permission(self, request):
        return False
