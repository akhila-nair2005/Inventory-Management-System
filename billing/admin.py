from django.contrib import admin

# Register your models here.
from .models import Customer, Invoice, InvoiceItem






from .models import Customer, Invoice, InvoiceItem
from accounts.permissions import RoleRestrictedAdminMixin


@admin.register(Customer)
class CustomerAdmin(RoleRestrictedAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'phone', 'email']
    search_fields = ['name', 'phone']
    allowed_roles_add = ['ADMIN', 'MANAGER', 'STAFF']  # Staff register walk-in customers at checkout
    allowed_roles_change = ['ADMIN', 'MANAGER', 'STAFF']


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1


@admin.register(Invoice)
class InvoiceAdmin(RoleRestrictedAdminMixin, admin.ModelAdmin):
    list_display = ['invoice_number', 'customer', 'status', 'total_amount', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['invoice_number']
    inlines = [InvoiceItemInline]
    allowed_roles_add = ['ADMIN', 'MANAGER', 'STAFF']  # Staff process sales/checkout daily
    allowed_roles_change = ['ADMIN', 'MANAGER']         # Only Manager+ can modify an existing invoice (e.g. status)
    allowed_roles_delete = ['ADMIN']                    # Only Admin can delete billing records