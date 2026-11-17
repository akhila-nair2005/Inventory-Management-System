"""Remembers which user is handling the current request so model signals can log them."""
from contextvars import ContextVar

_current_user = ContextVar('audit_current_user', default=None)


def get_current_user_id():
    """Primary key of the logged-in user for this request, or None (management command, etc.)."""
    user = _current_user.get()
    if user is not None and getattr(user, 'is_authenticated', False):
        return user.pk
    return None


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current_user.set(getattr(request, 'user', None))
        try:
            return self.get_response(request)
        finally:
            _current_user.reset(token)
