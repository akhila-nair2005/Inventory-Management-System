from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from .models import Invoice, InvoiceItem, Customer
from inventory.models import Product, StockMovement
import uuid


@login_required
def invoice_list(request):
    invoices = Invoice.objects.select_related('customer').all().order_by('-created_at')
    return render(request, 'billing/invoice_list.html', {'invoices': invoices})


@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    return render(request, 'billing/invoice_detail.html', {'invoice': invoice})


@login_required
def invoice_create(request):
    # Staff, Manager, Admin can all create invoices (checkout is a daily task)
    products = Product.objects.filter(quantity__gt=0)
    customers = Customer.objects.all()

    if request.method == 'POST':
        customer_id = request.POST.get('customer')
        new_customer_name = request.POST.get('new_customer_name')

        with transaction.atomic():
            if new_customer_name:
                customer = Customer.objects.create(name=new_customer_name)
            elif customer_id:
                customer = Customer.objects.get(pk=customer_id)
            else:
                customer = None

            invoice = Invoice.objects.create(
                invoice_number=f"INV-{uuid.uuid4().hex[:8].upper()}",
                customer=customer,
                created_by=request.user,
                status='PENDING',
            )

            product_ids = request.POST.getlist('product')
            quantities = request.POST.getlist('quantity')

            for prod_id, qty in zip(product_ids, quantities):
                if prod_id and qty:
                    qty = int(qty)
                    product = Product.objects.get(pk=prod_id)
                    if qty > product.quantity:
                        messages.error(request, f"Not enough stock for {product.name}.")
                        invoice.delete()
                        return redirect('invoice_create')

                    InvoiceItem.objects.create(
                        invoice=invoice,
                        product=product,
                        quantity=qty,
                        unit_price=product.price,
                    )
                    # Record the stock-out movement (this auto-decrements Product.quantity)
                    StockMovement.objects.create(
                        product=product,
                        movement_type='OUT',
                        quantity=qty,
                        performed_by=request.user,
                        note=f"Sold via {invoice.invoice_number}",
                    )

        messages.success(request, f"Invoice {invoice.invoice_number} created.")
        return redirect('invoice_detail', pk=invoice.pk)

    return render(request, 'billing/invoice_form.html', {
        'products': products,
        'customers': customers,
    })

@login_required
def mark_invoice_paid(request, pk):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "You don't have permission to update invoice status.")
        return redirect('invoice_detail', pk=pk)

    invoice = get_object_or_404(Invoice, pk=pk)
    invoice.status = 'PAID'
    invoice.save()
    messages.success(request, f"Invoice {invoice.invoice_number} marked as paid.")
    return redirect('invoice_detail', pk=pk)