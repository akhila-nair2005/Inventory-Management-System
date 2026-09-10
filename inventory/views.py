from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Product, Category, Supplier



@login_required
def product_list(request):
    products = Product.objects.select_related('category', 'supplier').all()
    return render(request, 'inventory/product_list.html', {'products': products})


@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    return render(request, 'inventory/product_detail.html', {'product': product})


@login_required
def product_create(request):
    # Only Admin and Manager can add products
    if request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "You don't have permission to add products.")
        return redirect('product_list')

    categories = Category.objects.all()
    suppliers = Supplier.objects.all()

    if request.method == 'POST':
        Product.objects.create(
            name=request.POST.get('name'),
            sku=request.POST.get('sku'),
            barcode=request.POST.get('barcode') or None,
            category_id=request.POST.get('category') or None,
            supplier_id=request.POST.get('supplier') or None,
            price=request.POST.get('price'),
            quantity=request.POST.get('quantity') or 0,
            reorder_level=request.POST.get('reorder_level') or 10,
        )
        messages.success(request, "Product added successfully.")
        return redirect('product_list')

    return render(request, 'inventory/product_form.html', {
        'categories': categories,
        'suppliers': suppliers,
    })

#Stock Movement recording (Staff's daily task)

from .models import Product, Category, Supplier, StockMovement

@login_required
def stock_movement_create(request):
    products = Product.objects.all()

    if request.method == 'POST':
        product = get_object_or_404(Product, pk=request.POST.get('product'))
        movement_type = request.POST.get('movement_type')
        quantity = int(request.POST.get('quantity'))

        if movement_type == 'OUT' and quantity > product.quantity:
            messages.error(request, f"Cannot remove {quantity} units — only {product.quantity} in stock.")
            return redirect('stock_movement_create')

        StockMovement.objects.create(
            product=product,
            movement_type=movement_type,
            quantity=quantity,
            performed_by=request.user,
            note=request.POST.get('note', ''),
        )
        messages.success(request, f"Stock movement recorded for {product.name}.")
        return redirect('product_list')

    return render(request, 'inventory/stock_movement_form.html', {'products': products})

#generate barcode images
from django.http import HttpResponse
import barcode
from barcode.writer import ImageWriter
from io import BytesIO


@login_required
def barcode_image(request, pk):
    product = get_object_or_404(Product, pk=pk)

    if not product.barcode:
        return HttpResponse(status=404)

    try:
        barcode_class = barcode.get_barcode_class('code128')
        code = barcode_class(product.barcode, writer=ImageWriter())
        buffer = BytesIO()
        code.write(buffer, options={'write_text': True, 'module_height': 8})
        buffer.seek(0)
        return HttpResponse(buffer.getvalue(), content_type='image/png')
    except Exception:
        return HttpResponse(status=400)

from django.http import JsonResponse

def barcode_lookup(request):
    code = request.GET.get('code', '').strip()
    try:
        product = Product.objects.get(barcode=code)
        return JsonResponse({'found': True, 'product_id': product.id, 'name': product.name})
    except Product.DoesNotExist:
        return JsonResponse({'found': False})

from django.db import transaction
from django.utils import timezone
import uuid
from .models import PurchaseOrder, PurchaseOrderItem


@login_required
def purchase_order_list(request):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "You don't have permission to view purchase orders.")
        return redirect('dashboard')

    orders = PurchaseOrder.objects.select_related('supplier').all().order_by('-order_date')
    return render(request, 'inventory/purchase_order_list.html', {'orders': orders})


@login_required
def purchase_order_detail(request, pk):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "You don't have permission to view purchase orders.")
        return redirect('dashboard')

    order = get_object_or_404(PurchaseOrder, pk=pk)
    return render(request, 'inventory/purchase_order_detail.html', {'order': order})


@login_required
def purchase_order_create(request):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "You don't have permission to create purchase orders.")
        return redirect('dashboard')

    suppliers = Supplier.objects.all()
    products = Product.objects.all()

    if request.method == 'POST':
        supplier = get_object_or_404(Supplier, pk=request.POST.get('supplier'))

        with transaction.atomic():
            order = PurchaseOrder.objects.create(
                order_number=f"PO-{uuid.uuid4().hex[:8].upper()}",
                supplier=supplier,
                created_by=request.user,
                notes=request.POST.get('notes', ''),
            )

            product_ids = request.POST.getlist('product')
            quantities = request.POST.getlist('quantity')
            costs = request.POST.getlist('unit_cost')

            for prod_id, qty, cost in zip(product_ids, quantities, costs):
                if prod_id and qty and cost:
                    PurchaseOrderItem.objects.create(
                        purchase_order=order,
                        product_id=prod_id,
                        quantity_ordered=int(qty),
                        unit_cost=cost,
                    )

        messages.success(request, f"Purchase order {order.order_number} created.")
        return redirect('purchase_order_detail', pk=order.pk)

    return render(request, 'inventory/purchase_order_form.html', {
        'suppliers': suppliers,
        'products': products,
    })


@login_required
def purchase_order_receive(request, pk):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "You don't have permission to receive purchase orders.")
        return redirect('purchase_order_list')

    order = get_object_or_404(PurchaseOrder, pk=pk)

    if order.status != 'PENDING':
        messages.error(request, "This order has already been processed.")
        return redirect('purchase_order_detail', pk=pk)

    with transaction.atomic():
        for item in order.items.all():
            StockMovement.objects.create(
                product=item.product,
                movement_type='IN',
                quantity=item.quantity_ordered,
                performed_by=request.user,
                note=f"Received from PO {order.order_number}",
            )
        order.status = 'RECEIVED'
        order.received_date = timezone.now()
        order.save()

    messages.success(request, f"Order {order.order_number} marked as received. Stock updated.")
    return redirect('purchase_order_detail', pk=pk)


@login_required
def purchase_order_cancel(request, pk):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "You don't have permission to cancel purchase orders.")
        return redirect('purchase_order_list')

    order = get_object_or_404(PurchaseOrder, pk=pk)
    if order.status == 'PENDING':
        order.status = 'CANCELLED'
        order.save()
        messages.success(request, f"Order {order.order_number} cancelled.")
    return redirect('purchase_order_detail', pk=pk)