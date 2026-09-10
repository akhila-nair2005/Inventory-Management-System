from django.contrib import admin

# Register your models here.





from django.contrib import admin
from .models import Category, Supplier, Product, StockMovement
from accounts.permissions import RoleRestrictedAdminMixin


@admin.register(Category)
class CategoryAdmin(RoleRestrictedAdminMixin, admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']
    # Only Admin/Manager organize categories — Staff have no reason to


@admin.register(Supplier)
class SupplierAdmin(RoleRestrictedAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'phone', 'email']
    search_fields = ['name']
    # Supplier relationships are a Manager/Admin responsibility, not Staff


@admin.register(Product)
class ProductAdmin(RoleRestrictedAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'sku', 'category', 'quantity', 'reorder_level', 'is_low_stock']
    list_filter = ['category', 'supplier']
    search_fields = ['name', 'sku', 'barcode']
    # Staff can VIEW products (to check stock/prices) but not add/edit/delete
    # Pricing and product setup is a Manager/Admin decision

    def is_low_stock(self, obj):
        return obj.is_low_stock
    is_low_stock.boolean = True


@admin.register(StockMovement)
class StockMovementAdmin(RoleRestrictedAdminMixin, admin.ModelAdmin):
    list_display = ['product', 'movement_type', 'quantity', 'performed_by', 'timestamp']
    list_filter = ['movement_type', 'timestamp']
    allowed_roles_add = ['ADMIN', 'MANAGER', 'STAFF']  # Staff log stock daily — core job duty
    allowed_roles_change = ['ADMIN', 'MANAGER']         # Staff can't edit past records (audit integrity)
    allowed_roles_delete = ['ADMIN']   

from .models import Category, Supplier, Product, StockMovement, PurchaseOrder, PurchaseOrderItem


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(RoleRestrictedAdminMixin, admin.ModelAdmin):
    list_display = ['order_number', 'supplier', 'status', 'total_cost', 'order_date']
    list_filter = ['status', 'supplier']
    inlines = [PurchaseOrderItemInline]
    allowed_roles_add = ['ADMIN', 'MANAGER']
    allowed_roles_change = ['ADMIN', 'MANAGER']
    allowed_roles_delete = ['ADMIN']                 # Only Admin can delete movement history