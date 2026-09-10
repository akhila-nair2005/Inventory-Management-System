

# Register your models here.




from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ['username', 'email', 'role', 'is_staff', 'is_active']
    list_filter = ['role', 'is_staff', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('Role Info', {'fields': ('role',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role Info', {'fields': ('role',)}),
    )

    def has_module_permission(self, request):
        return request.user.is_superuser or getattr(request.user, 'role', None) == 'ADMIN'

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or getattr(request.user, 'role', None) == 'ADMIN'

    def has_add_permission(self, request):
        return request.user.is_superuser or getattr(request.user, 'role', None) == 'ADMIN'

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or getattr(request.user, 'role', None) == 'ADMIN'

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser or getattr(request.user, 'role', None) == 'ADMIN'


admin.site.register(User, CustomUserAdmin)