

# Create your views here.
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from inventory.models import Product, PurchaseOrder
from billing.models import Invoice
from alerts.models import StockAlert


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
    today = timezone.now().date()

    total_products = Product.objects.count()
    low_stock_count = sum(1 for p in Product.objects.all() if p.is_low_stock)
    pending_orders_count = PurchaseOrder.objects.filter(
        status__in=['PENDING', 'PARTIALLY_RECEIVED']
    ).count()

    todays_invoices = Invoice.objects.filter(created_at__date=today)
    todays_sales = sum(inv.total_amount for inv in todays_invoices)

    context = {
        'user': request.user,
        'total_products': total_products,
        'low_stock_count': low_stock_count,
        'pending_orders_count': pending_orders_count,
        'todays_sales': todays_sales,
    }
    return render(request, 'accounts/dashboard.html', context)

def landing_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'accounts/landing.html')