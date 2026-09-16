from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Product, Category, Supplier
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Sum
from billing.models import Invoice, InvoiceItem
from datetime import timedelta



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
from .models import (
    Product, Category, Supplier, StockMovement,
    PurchaseOrder, PurchaseOrderItem, GoodsReceipt, GoodsReceiptItem
)


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


# @login_required
# def send_po_email_to_supplier(order):
#     if not order.supplier.email:
#         return
#     items_text = "\n".join(
#         f"- {item.product.name}: {item.quantity_ordered} units @ ₹{item.unit_cost} each"
#         for item in order.items.all()
#     )
#     send_mail(
#         subject=f"New Purchase Order: {order.order_number}",
#         message=(
#             f"Dear {order.supplier.contact_person or order.supplier.name},\n\n"
#             f"We would like to place the following order:\n\n"
#             f"{items_text}\n\n"
#             f"Grand Total: ₹{order.grand_total}\n"
#             f"Requested Delivery Date: {order.expected_delivery_date or 'Not specified'}\n"
#             f"Delivery Address: {order.delivery_address or 'Not specified'}\n"
#             f"Payment Terms: {order.payment_terms}\n\n"
#             f"Please confirm receipt and expected delivery date.\n\n"
#             f"Regards,\nStockMS"
#         ),
#         from_email=settings.DEFAULT_FROM_EMAIL,
#         recipient_list=[order.supplier.email],
#         fail_silently=True,
#     )
#     for w in margin_warnings:
#         messages.warning(request, w)
#     send_po_email_to_supplier(order)
#     messages.success(request, f"Purchase order {order.order_number} created and emailed to supplier.")
#     return redirect('purchase_order_detail', pk=order.pk)
# def purchase_order_create(request):
#     if request.user.role not in ['ADMIN', 'MANAGER']:
#         messages.error(request, "You don't have permission to create purchase orders.")
#         return redirect('dashboard')

#     suppliers = Supplier.objects.all()
#     # Only show products with their suggested reorder quantity for convenience
#     products = Product.objects.all()

#     if request.method == 'POST':
#         supplier = get_object_or_404(Supplier, pk=request.POST.get('supplier'))

#         with transaction.atomic():
#             order = PurchaseOrder.objects.create(
#                 order_number=f"PO-{timezone.now().year}-{uuid.uuid4().hex[:6].upper()}",
#                 supplier=supplier,
#                 created_by=request.user,
#                 expected_delivery_date=request.POST.get('expected_delivery_date') or None,
#                 payment_terms=request.POST.get('payment_terms', 'Due on delivery'),
#                 delivery_address=request.POST.get('delivery_address', ''),
#                 tax_percent=request.POST.get('tax_percent') or 0,
#                 discount_amount=request.POST.get('discount_amount') or 0,
#                 notes=request.POST.get('notes', ''),
#             )

#             product_ids = request.POST.getlist('product')
#             quantities = request.POST.getlist('quantity')
#             costs = request.POST.getlist('unit_cost')

#             margin_warnings = []

#             for prod_id, qty, cost in zip(product_ids, quantities, costs):
#                 if prod_id and qty and cost:
#                     product = Product.objects.get(pk=prod_id)
#                     unit_cost = float(cost)

#                     if unit_cost >= float(product.price):
#                         margin_warnings.append(
#                             f"{product.name}: cost (₹{unit_cost}) is not lower than selling price (₹{product.price})."
#                         )

#                     PurchaseOrderItem.objects.create(
#                         purchase_order=order,
#                         product_id=prod_id,
#                         quantity_ordered=int(qty),
#                         unit_cost=unit_cost,
#                     )
        
#         for w in margin_warnings:
#             messages.warning(request, w)
#         messages.success(request, f"Purchase order {order.order_number} created. Stock will update only after goods are received.")
#         return redirect('purchase_order_detail', pk=order.pk)

#     return render(request, 'inventory/purchase_order_form.html', {
#         'suppliers': suppliers,
#         'products': products,
#     })

def send_po_email_to_supplier(order):
    if not order.supplier.email:
        return
    items_text = "\n".join(
        f"- {item.product.name}: {item.quantity_ordered} units @ ₹{item.unit_cost} each"
        for item in order.items.all()
    )
    send_mail(
        subject=f"New Purchase Order: {order.order_number}",
        message=(
            f"Dear {order.supplier.contact_person or order.supplier.name},\n\n"
            f"We would like to place the following order:\n\n"
            f"{items_text}\n\n"
            f"Grand Total: ₹{order.grand_total}\n"
            f"Requested Delivery Date: {order.expected_delivery_date or 'Not specified'}\n"
            f"Delivery Address: {order.delivery_address or 'Not specified'}\n"
            f"Payment Terms: {order.payment_terms}\n\n"
            f"Please confirm receipt and expected delivery date.\n\n"
            f"Regards,\nStockMS"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.supplier.email],
        fail_silently=True,
    )


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
                order_number=f"PO-{timezone.now().year}-{uuid.uuid4().hex[:6].upper()}",
                supplier=supplier,
                created_by=request.user,
                expected_delivery_date=request.POST.get('expected_delivery_date') or None,
                payment_terms=request.POST.get('payment_terms', 'Due on delivery'),
                delivery_address=request.POST.get('delivery_address', ''),
                tax_percent=request.POST.get('tax_percent') or 0,
                discount_amount=request.POST.get('discount_amount') or 0,
                notes=request.POST.get('notes', ''),
            )

            product_ids = request.POST.getlist('product')
            quantities = request.POST.getlist('quantity')
            costs = request.POST.getlist('unit_cost')

            margin_warnings = []

            for prod_id, qty, cost in zip(product_ids, quantities, costs):
                if prod_id and qty and cost:
                    product = Product.objects.get(pk=prod_id)
                    unit_cost = float(cost)

                    if unit_cost >= float(product.price):
                        margin_warnings.append(
                            f"{product.name}: cost (₹{unit_cost}) is not lower than selling price (₹{product.price})."
                        )

                    PurchaseOrderItem.objects.create(
                        purchase_order=order,
                        product_id=prod_id,
                        quantity_ordered=int(qty),
                        unit_cost=unit_cost,
                    )

        for w in margin_warnings:
            messages.warning(request, w)
        send_po_email_to_supplier(order)
        messages.success(request, f"Purchase order {order.order_number} created and emailed to supplier.")
        return redirect('purchase_order_detail', pk=order.pk)

    return render(request, 'inventory/purchase_order_form.html', {
        'suppliers': suppliers,
        'products': products,
    })

@login_required
def purchase_order_confirm_delivery(request, pk):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "You don't have permission to do this.")
        return redirect('purchase_order_detail', pk=pk)

    order = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == 'POST':
        order.confirmed_delivery_date = request.POST.get('confirmed_delivery_date')
        order.save()
        messages.success(request, "Confirmed delivery date recorded.")
    return redirect('purchase_order_detail', pk=pk)

# @login_required
# def purchase_order_receive(request, pk):
#     if request.user.role not in ['ADMIN', 'MANAGER']:
#         messages.error(request, "You don't have permission to receive purchase orders.")
#         return redirect('purchase_order_list')

#     order = get_object_or_404(PurchaseOrder, pk=pk)

#     if order.status in ['RECEIVED', 'CANCELLED']:
#         messages.error(request, "This order is already closed.")
#         return redirect('purchase_order_detail', pk=pk)

#     if request.method == 'POST':
#         with transaction.atomic():
#             receipt = GoodsReceipt.objects.create(
#                 purchase_order=order,
#                 received_by=request.user,
#                 remarks=request.POST.get('remarks', ''),
#             )

#             all_fully_received = True

#             for item in order.items.all():
#                 received = request.POST.get(f'received_{item.id}')
#                 damaged = request.POST.get(f'damaged_{item.id}')

#                 if received:
#                     received = int(received)
#                     damaged = int(damaged) if damaged else 0

#                     receipt_item = GoodsReceiptItem.objects.create(
#                         receipt=receipt,
#                         po_item=item,
#                         quantity_received=received,
#                         quantity_damaged=damaged,
#                     )

#                     # Only usable (non-damaged) units get added to sellable stock
#                     if receipt_item.usable_quantity > 0:
#                         StockMovement.objects.create(
#                             product=item.product,
#                             movement_type='IN',
#                             quantity=receipt_item.usable_quantity,
#                             performed_by=request.user,
#                             note=f"Received from {order.order_number} (Receipt #{receipt.id})",
#                         )

#                 if not item.is_fully_received:
#                     all_fully_received = False

#             order.status = PurchaseOrder.Status.RECEIVED if all_fully_received else PurchaseOrder.Status.PARTIALLY_RECEIVED
#             order.save()

#         messages.success(request, f"Goods receipt recorded for {order.order_number}.")
#         return redirect('purchase_order_detail', pk=pk)

#     return render(request, 'inventory/goods_receipt_form.html', {'order': order})

def send_discrepancy_email(order, receipt):
    problems = []
    for receipt_item in receipt.items.all():
        po_item = receipt_item.po_item
        shortfall = po_item.quantity_ordered - receipt_item.quantity_received
        if shortfall > 0 or receipt_item.quantity_damaged > 0:
            problems.append(
                f"- {po_item.product.name}: ordered {po_item.quantity_ordered}, "
                f"received {receipt_item.quantity_received}, damaged {receipt_item.quantity_damaged}"
                + (f", short by {shortfall}" if shortfall > 0 else "")
            )

    if problems and order.supplier.email:
        send_mail(
            subject=f"Discrepancy in Delivery for {order.order_number}",
            message=(
                f"Dear {order.supplier.contact_person or order.supplier.name},\n\n"
                f"We received the delivery for order {order.order_number}, but found the following issues:\n\n"
                + "\n".join(problems) +
                f"\n\nPlease advise on replacement or credit for the affected items.\n\nRegards,\nStockMS"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.supplier.email],
            fail_silently=True,
        )


@login_required
def purchase_order_receive(request, pk):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "You don't have permission to receive purchase orders.")
        return redirect('purchase_order_list')

    order = get_object_or_404(PurchaseOrder, pk=pk)

    if order.status in ['RECEIVED', 'CANCELLED']:
        messages.error(request, "This order is already closed.")
        return redirect('purchase_order_detail', pk=pk)

    if request.method == 'POST':
        with transaction.atomic():
            receipt = GoodsReceipt.objects.create(
                purchase_order=order,
                received_by=request.user,
                remarks=request.POST.get('remarks', ''),
            )

            all_fully_received = True

            for item in order.items.all():
                received = request.POST.get(f'received_{item.id}')
                damaged = request.POST.get(f'damaged_{item.id}')

                if received:
                    received = int(received)
                    damaged = int(damaged) if damaged else 0

                    receipt_item = GoodsReceiptItem.objects.create(
                        receipt=receipt,
                        po_item=item,
                        quantity_received=received,
                        quantity_damaged=damaged,
                    )

                    # Only usable (non-damaged) units get added to sellable stock
                    if receipt_item.usable_quantity > 0:
                        StockMovement.objects.create(
                            product=item.product,
                            movement_type='IN',
                            quantity=receipt_item.usable_quantity,
                            performed_by=request.user,
                            note=f"Received from {order.order_number} (Receipt #{receipt.id})",
                        )

                if not item.is_fully_received:
                    all_fully_received = False

            order.status = PurchaseOrder.Status.RECEIVED if all_fully_received else PurchaseOrder.Status.PARTIALLY_RECEIVED
            order.save()

        send_discrepancy_email(order, receipt)
        messages.success(request, f"Goods receipt recorded for {order.order_number}.")
        return redirect('purchase_order_detail', pk=pk)

    return render(request, 'inventory/goods_receipt_form.html', {'order': order})
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



@login_required
def supplier_list(request):
    suppliers = Supplier.objects.all()
    return render(request, 'inventory/supplier_list.html', {'suppliers': suppliers})


@login_required
def supplier_detail(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    products = supplier.products.all()
    orders = supplier.purchase_orders.all().order_by('-order_date')[:10]
    return render(request, 'inventory/supplier_detail.html', {
        'supplier': supplier, 'products': products, 'orders': orders,
    })


@login_required
def supplier_create(request):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "You don't have permission to add suppliers.")
        return redirect('supplier_list')

    if request.method == 'POST':
        Supplier.objects.create(
            name=request.POST.get('name'),
            contact_person=request.POST.get('contact_person'),
            phone=request.POST.get('phone'),
            email=request.POST.get('email'),
            address=request.POST.get('address'),
            gst_number=request.POST.get('gst_number'),
        )
        messages.success(request, "Supplier added successfully.")
        return redirect('supplier_list')

    return render(request, 'inventory/supplier_form.html')



@login_required
def reports_page(request):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "You don't have permission to view reports.")
        return redirect('dashboard')

    # Total inventory value = sum of (quantity * price) across all products
    products = Product.objects.all()
    total_inventory_value = sum(p.quantity * p.price for p in products)

    # Top 5 best-selling products by total quantity sold
    top_products = (
        InvoiceItem.objects.values('product__name')
        .annotate(total_sold=Sum('quantity'))
        .order_by('-total_sold')[:5]
    )

    # Revenue over the last 14 days
    today = timezone.now().date()
    revenue_by_day = []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        invoices = Invoice.objects.filter(created_at__date=day)
        day_total = sum(inv.total_amount for inv in invoices)
        revenue_by_day.append({'date': day.strftime('%d %b'), 'total': float(day_total)})

    low_stock_products = [p for p in products if p.is_low_stock]

    context = {
        'total_inventory_value': total_inventory_value,
        'top_products': top_products,
        'revenue_labels': [d['date'] for d in revenue_by_day],
        'revenue_values': [d['total'] for d in revenue_by_day],
        'low_stock_products': low_stock_products,
    }
    return render(request, 'inventory/reports.html', context)