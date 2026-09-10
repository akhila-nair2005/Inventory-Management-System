

# Create your views here.
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse_lazy


class RoleBasedLoginView(LoginView):
    template_name = 'accounts/login.html'

    def get_success_url(self):
        user = self.request.user
        if user.role == 'ADMIN':
            return reverse_lazy('dashboard')
        elif user.role == 'MANAGER':
            return reverse_lazy('dashboard')
        else:
            return reverse_lazy('dashboard')


class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('login')


@login_required
def dashboard(request):
    return render(request, 'accounts/dashboard.html', {'user': request.user})