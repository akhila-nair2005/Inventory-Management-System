import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from alerts.models import EmailLog
from alerts.services import dispatch_email
from inventory.models import Product, StockMovement

from .models import Customer, Invoice, InvoiceItem
from .pdf import build_invoice_pdf

MANAGER_ROLES = ['ADMIN', 'MANAGER']


@login_required
def invoice_list(request):
    invoices = Invoice.objects.select_related('customer').prefetch_related('items').order_by('-created_at')

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    payment = request.GET.get('payment', '')
    if q:
        invoices = invoices.filter(Q(invoice_number__icontains=q) | Q(customer__name__icontains=q))
    if status:
        invoices = invoices.filter(status=status)
    if payment:
        invoices = invoices.filter(payment_method=payment)

    page = Paginator(invoices, 25).get_page(request.GET.get('page'))
    page_total = sum(inv.total_amount for inv in page if inv.status != 'CANCELLED')

    return render(request, 'billing/invoice_list.html', {
        'page': page,
        'q': q, 'status': status, 'payment': payment,
        'status_choices': Invoice.Status.choices,
        'payment_choices': Invoice.PaymentMethod.choices,
        'page_total': page_total,
    })


@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer', 'created_by').prefetch_related('items__product'), pk=pk
    )
    return render(request, 'billing/invoice_detail.html', {
        'invoice': invoice,
        'is_manager': request.user.role in MANAGER_ROLES,
    })


def _parse_decimal(value, default='0'):
    try:
        return Decimal(str(value or default))
    except InvalidOperation:
        return None


@login_required
def invoice_create(request):
    # Staff, Manager, Admin can all create invoices (checkout is a daily task)
    products = Product.objects.filter(quantity__gt=0).order_by('name')
    customers = Customer.objects.all().order_by('name')

    if request.method == 'POST':
        # 1. Read and validate everything BEFORE writing anything
        lines = {}
        for prod_id, qty in zip(request.POST.getlist('product'), request.POST.getlist('quantity')):
            if prod_id and qty:
                try:
                    qty_int = int(qty)
                    lines[int(prod_id)] = lines.get(int(prod_id), 0) + qty_int
                except ValueError:
                    continue
        lines = {pid: q for pid, q in lines.items() if q > 0}
        if not lines:
            messages.error(request, "Add at least one product with a quantity.")
            return redirect('invoice_create')

        tax_percent = _parse_decimal(request.POST.get('tax_percent'))
        discount = _parse_decimal(request.POST.get('discount_amount'))
        if tax_percent is None or discount is None or tax_percent < 0 or discount < 0 or tax_percent > 100:
            messages.error(request, "Tax must be 0-100 and discount must be a positive number.")
            return redirect('invoice_create')

        payment_method = request.POST.get('payment_method', 'CASH')
        if payment_method not in Invoice.PaymentMethod.values:
            payment_method = Invoice.PaymentMethod.CASH

        with transaction.atomic():
            locked = {p.pk: p for p in Product.objects.select_for_update().filter(pk__in=lines.keys())}
            problems = []
            for prod_id, qty in lines.items():
                product = locked.get(prod_id)
                if product is None:
                    problems.append("A selected product no longer exists.")
                elif qty > product.quantity:
                    problems.append(f"Not enough stock for {product.name}: {product.quantity} available, {qty} requested.")
            subtotal = sum(locked[pid].price * q for pid, q in lines.items() if pid in locked)
            if discount > subtotal:
                problems.append("Discount cannot be larger than the invoice subtotal.")
            if problems:
                for problem in problems:
                    messages.error(request, problem)
                return redirect('invoice_create')   # nothing has been written yet

            new_name = request.POST.get('new_customer_name', '').strip()
            customer_id = request.POST.get('customer')
            if new_name:
                customer = Customer.objects.create(
                    name=new_name,
                    phone=request.POST.get('new_customer_phone', '').strip(),
                    email=request.POST.get('new_customer_email', '').strip(),
                )
            elif customer_id:
                customer = Customer.objects.get(pk=customer_id)
            else:
                customer = None

            invoice = Invoice.objects.create(
                invoice_number=f"INV-{uuid.uuid4().hex[:8].upper()}",
                customer=customer,
                created_by=request.user,
                status='PENDING',
                payment_method=payment_method,
                tax_percent=tax_percent,
                discount_amount=discount,
            )
            for prod_id, qty in lines.items():
                product = locked[prod_id]
                InvoiceItem.objects.create(
                    invoice=invoice, product=product, quantity=qty,
                    unit_price=product.price, unit_cost=product.cost_price,
                )
                # Records the stock-out and decrements Product.quantity (may raise a stock alert)
                StockMovement.objects.create(
                    product=product, movement_type='OUT', quantity=qty,
                    performed_by=request.user, note=f"Sold via {invoice.invoice_number}",
                )

        messages.success(request, f"Invoice {invoice.invoice_number} created.")
        if request.POST.get('email_invoice') and customer and customer.email:
            _email_invoice(request, invoice)
        return redirect('invoice_detail', pk=invoice.pk)

    return render(request, 'billing/invoice_form.html', {
        'products': products,
        'customers': customers,
        'payment_choices': Invoice.PaymentMethod.choices,
    })


@login_required
def mark_invoice_paid(request, pk):
    if request.user.role not in MANAGER_ROLES:
        messages.error(request, "You don't have permission to update invoice status.")
        return redirect('invoice_detail', pk=pk)

    invoice = get_object_or_404(Invoice, pk=pk)
    if invoice.status == 'CANCELLED':
        messages.error(request, "A cancelled invoice cannot be marked as paid.")
        return redirect('invoice_detail', pk=pk)
    invoice.status = 'PAID'
    invoice.save()
    messages.success(request, f"Invoice {invoice.invoice_number} marked as paid.")
    return redirect('invoice_detail', pk=pk)


@login_required
@require_POST
def invoice_cancel(request, pk):
    """Cancel an invoice and put its items back into stock."""
    if request.user.role not in MANAGER_ROLES:
        messages.error(request, "You don't have permission to cancel invoices.")
        return redirect('invoice_detail', pk=pk)

    invoice = get_object_or_404(Invoice, pk=pk)
    if invoice.status == 'CANCELLED':
        messages.info(request, "This invoice is already cancelled.")
        return redirect('invoice_detail', pk=pk)

    with transaction.atomic():
        for item in invoice.items.select_related('product'):
            StockMovement.objects.create(
                product=item.product, movement_type='IN', quantity=item.quantity,
                performed_by=request.user, note=f"Returned: {invoice.invoice_number} cancelled",
            )
        invoice.status = 'CANCELLED'
        invoice.save()
    messages.success(request, f"Invoice {invoice.invoice_number} cancelled and stock restored.")
    return redirect('invoice_detail', pk=pk)


@login_required
def invoice_pdf(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related('customer'), pk=pk)
    response = HttpResponse(build_invoice_pdf(invoice), content_type='application/pdf')
    disposition = 'attachment' if request.GET.get('download') else 'inline'
    response['Content-Disposition'] = f'{disposition}; filename="{invoice.invoice_number}.pdf"'
    return response


def _email_invoice(request, invoice):
    customer = invoice.customer
    if not (customer and customer.email):
        messages.warning(request, "This customer has no e-mail address.")
        return False
    sent = dispatch_email(
        subject=f"Your invoice {invoice.invoice_number}",
        body=(
            f"Dear {customer.name},\n\nThank you for your purchase. "
            f"Your invoice {invoice.invoice_number} for \u20b9{invoice.total_amount} is attached.\n\nRegards,\nStockMS"
        ),
        recipients=[customer.email],
        alert_type=EmailLog.AlertType.INVOICE,
        triggered_by=request.user,
        attachments=[(f"{invoice.invoice_number}.pdf", build_invoice_pdf(invoice), 'application/pdf')],
    )
    if sent:
        messages.success(request, f"Invoice e-mailed to {customer.email}.")
    else:
        messages.error(request, "The invoice e-mail could not be sent. See the Email Log.")
    return sent


@login_required
@require_POST
def invoice_email(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related('customer'), pk=pk)
    _email_invoice(request, invoice)
    return redirect('invoice_detail', pk=pk)
