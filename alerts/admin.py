from django.contrib import admin

# Register your models here.
from .models import StockAlert




#read-only, system-generated
from accounts.permissions import RoleRestrictedAdminMixin


@admin.register(StockAlert)
class StockAlertAdmin(RoleRestrictedAdminMixin, admin.ModelAdmin):
    list_display = ['product', 'quantity_at_alert', 'reorder_level_at_alert', 'resolved', 'created_at']
    list_filter = ['resolved', 'created_at']
    allowed_roles_add = []                       # Nobody manually creates alerts — only the signal does
    allowed_roles_change = ['ADMIN', 'MANAGER']   # Manager marks alerts as resolved once restocked
    allowed_roles_delete = ['ADMIN']

    def has_add_permission(self, request):
        return False  # Alerts are system-generated only, never manual