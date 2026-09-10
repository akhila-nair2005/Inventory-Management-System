from django.contrib import admin

# Register your models here.

#Admin only visibility
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'model_name', 'object_id', 'object_repr', 'user', 'timestamp']
    list_filter = ['action', 'model_name', 'timestamp']
    search_fields = ['object_repr', 'object_id']
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    #def has_module_permission(self, request):
       # return request.user.is_superuser or request.user.role == 'ADMIN'
    def has_module_permission(self, request):
        return request.user.is_superuser or getattr(request.user, 'role', None) == 'ADMIN'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser  # Even Admin shouldn't casually delete audit history
    

    