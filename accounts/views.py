import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST

from alerts.models import EmailLog, StockAlert
from billing import analytics
from billing.models import Invoice
from forecasting.forecasting_utils import get_all_forecasts, sort_by_urgency
from inventory.models import Product, PurchaseOrder

from .forms import StaffCreateForm, StaffUpdateForm
from .models import User


class RoleBasedLoginView(LoginView):
    template_name = 'accounts/login.html'

    def get_success_url(self):
        return reverse_lazy('dashboard')


class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('login')


def _admin_required(request):
    """Returns a redirect response when the user is not an Admin, otherwise None."""
    if request.user.role != 'ADMIN':
        messages.error(request, "Only Admins can manage staff accounts.")
        return redirect('dashboard')
    return None


@login_required
def dashboard(request):
    user = request.user
    is_manager_view = user.role in ('ADMIN', 'MANAGER')
    now = timezone.now()

    products = list(Product.objects.select_related('category').all())
    out_of_stock = [p for p in products if p.quantity == 0]
    low_stock = [p for p in products if 0 < p.quantity <= p.reorder_level]

    totals = analytics.sales_totals(now)
    active_alerts = StockAlert.objects.filter(resolved=False).select_related('product')

    context = {
        'is_manager_view': is_manager_view,
        'total_products': len(products),
        'total_units': sum(p.quantity for p in products),
        'category_count': len({p.category_id for p in products if p.category_id}),
        'low_stock_count': len(low_stock),
        'out_of_stock_count': len(out_of_stock),
        'pending_orders_count': PurchaseOrder.objects.filter(
            status__in=['PENDING', 'PARTIALLY_RECEIVED']
        ).count(),
        'todays_sales': totals['today'],
        'todays_invoice_count': Invoice.objects.filter(created_at__date=now.date()).exclude(status='CANCELLED').count(),
        'active_alerts': active_alerts[:6],
        'active_alert_total': active_alerts.count(),
        'recent_invoices': Invoice.objects.select_related('customer').prefetch_related('items')[:6],
    }

    stock_chart = {
        'labels': [p.sku for p in products],
        'names': [p.name for p in products],
        'values': [p.quantity for p in products],
        'colors': [
            '#dc2626' if p.quantity == 0 else '#f59e0b' if p.quantity <= p.reorder_level else '#475569'
            for p in products
        ],
    }
    chart_data = {'stock': stock_chart}

    if is_manager_view:
        monthly = analytics.monthly_sales(6, now)
        retail_value = sum(p.stock_value for p in products)
        cost_value = sum(p.stock_cost_value for p in products)

        by_category = {}
        for p in products:
            name = p.category.name if p.category else 'Uncategorised'
            by_category[name] = by_category.get(name, 0) + float(p.quantity * p.price)

        all_forecasts = [f for f in sort_by_urgency(get_all_forecasts()) if f['status'] == 'OK']
        restock_needed = sum(1 for f in all_forecasts if f['recommended_restock'] > 0)
        forecasts = sorted(all_forecasts, key=lambda f: -f['blended_next_month'])[:6]

        context.update({
            'revenue_total': totals['all_time'],
            'revenue_month': totals['this_month'],
            'profit_month': totals['month_profit'],
            'invoice_count': totals['invoice_count'],
            'procurement_spend': analytics.procurement_spend(),
            'po_count': PurchaseOrder.objects.exclude(status='CANCELLED').count(),
            'inventory_retail_value': retail_value,
            'inventory_cost_value': cost_value,
            'emails_sent': EmailLog.objects.count(),
            'restock_needed': restock_needed,
            'top_products': analytics.top_products(5),
        })
        chart_data.update({
            'revenue': {
                'labels': [m['label'] for m in monthly],
                'revenue': [float(m['revenue']) for m in monthly],
                'profit': [float(m['profit']) for m in monthly],
            },
            'category': {
                'labels': list(by_category.keys()),
                'values': [round(v, 2) for v in by_category.values()],
            },
            'forecasts': forecasts,
        })

    context['chart_data'] = chart_data
    return render(request, 'accounts/dashboard.html', context)


def landing_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'accounts/landing.html')


# ---------------------------------------------------------------- staff management

@login_required
def staff_list(request):
    denied = _admin_required(request)
    if denied:
        return denied

    users = User.objects.all().order_by('-is_active', 'role', 'username')
    q = request.GET.get('q', '').strip()
    role = request.GET.get('role', '')
    status = request.GET.get('status', '')
    if q:
        users = users.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
            | Q(email__icontains=q) | Q(department__icontains=q)
        )
    if role:
        users = users.filter(role=role)
    if status == 'active':
        users = users.filter(is_active=True)
    elif status == 'inactive':
        users = users.filter(is_active=False)

    return render(request, 'accounts/staff_list.html', {
        'users': users,
        'q': q, 'role': role, 'status': status,
        'roles': User.Role.choices,
        'total': User.objects.count(),
        'active_total': User.objects.filter(is_active=True).count(),
        'admin_total': User.objects.filter(role='ADMIN', is_active=True).count(),
    })


@login_required
def staff_create(request):
    denied = _admin_required(request)
    if denied:
        return denied

    form = StaffCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        messages.success(request, f"Account '{user.username}' created.")
        return redirect('staff_list')
    return render(request, 'accounts/staff_form.html', {'form': form, 'title': 'Add Staff Account'})


@login_required
def staff_update(request, pk):
    denied = _admin_required(request)
    if denied:
        return denied

    target = get_object_or_404(User, pk=pk)
    form = StaffUpdateForm(request.POST or None, instance=target)
    if request.method == 'POST' and form.is_valid():
        # Never let the last active Admin lock everyone out
        new_role, still_active = form.cleaned_data['role'], form.cleaned_data['is_active']
        others = User.objects.filter(role='ADMIN', is_active=True).exclude(pk=target.pk).count()
        if (new_role != 'ADMIN' or not still_active) and target.role == 'ADMIN' and others == 0:
            messages.error(request, "At least one active Admin account must remain.")
        else:
            form.save()
            messages.success(request, f"Account '{target.username}' updated.")
            return redirect('staff_list')
    return render(request, 'accounts/staff_form.html', {
        'form': form, 'title': f'Edit {target.username}', 'editing': target,
    })


@login_required
@require_POST
def staff_toggle_active(request, pk):
    denied = _admin_required(request)
    if denied:
        return denied

    target = get_object_or_404(User, pk=pk)
    if target.pk == request.user.pk:
        messages.error(request, "You can't deactivate your own account.")
        return redirect('staff_list')

    if target.is_active and target.role == 'ADMIN':
        if User.objects.filter(role='ADMIN', is_active=True).exclude(pk=target.pk).count() == 0:
            messages.error(request, "At least one active Admin account must remain.")
            return redirect('staff_list')

    target.is_active = not target.is_active
    target.save(update_fields=['is_active'])
    state = 'activated' if target.is_active else 'deactivated'
    messages.success(request, f"Account '{target.username}' {state}.")
    return redirect('staff_list')
