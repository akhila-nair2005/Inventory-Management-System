class RoleRestrictedAdminMixin:
    allowed_roles_view = ['ADMIN', 'MANAGER', 'STAFF']
    allowed_roles_add = ['ADMIN', 'MANAGER']
    allowed_roles_change = ['ADMIN', 'MANAGER']
    allowed_roles_delete = ['ADMIN']

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or getattr(request.user, 'role', None) in self.allowed_roles_view

    def has_add_permission(self, request):
        return request.user.is_superuser or getattr(request.user, 'role', None) in self.allowed_roles_add

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or getattr(request.user, 'role', None) in self.allowed_roles_change

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser or getattr(request.user, 'role', None) in self.allowed_roles_delete