import uuid
from io import BytesIO

import barcode
from barcode.writer import ImageWriter
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from alerts.models import EmailLog, StockAlert
from alerts.services import dispatch_email
from billing import analytics
from forecasting.forecasting_utils import get_all_forecasts, sort_by_urgency

from .forms import CategoryForm, ProductForm
from .models import (
    Category, GoodsReceipt, GoodsReceiptItem, Product, PurchaseOrder,
    PurchaseOrderItem, StockMovement, Supplier,
)

MANAGER_ROLES = ['ADMIN', 'MANAGER']


# --------------------------------------------------------------------------- products

@login_required
def product_list(request):
    products = Product.objects.select_related('category', 'supplier')

    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')
    status = request.GET.get('status', '')

    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(sku__icontains=q) | Q(brand__icontains=q) | Q(barcode__icontains=q)
        )
    if category.isdigit():
        products = products.filter(category_id=int(category))

    products = list(products.order_by('name'))
    if status == 'out':
        products = [p for p in products if p.quantity == 0]
    elif status == 'low':
        products = [p for p in products if 0 < p.quantity <= p.reorder_level]
    elif status == 'ok':
        products = [p for p in products if p.quantity > p.reorder_level]

    return render(request, 'inventory/product_list.html', {
        'products': products,
        'categories': Category.objects.all(),
        'q': q,
        'category': category,
        'status': status,
        'can_edit': request.user.role in MANAGER_ROLES,
    })


@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product.objects.select_related('category', 'supplier'), pk=pk)
    movements = product.movements.select_related('performed_by').order_by('-timestamp')[:10]
    return render(request, 'inventory/product_detail.html', {
        'product': product,
        'movements': movements,
        'can_edit': request.user.role in MANAGER_ROLES,
    })


def _assign_barcode_if_missing(product):
    """Give the product a unique 12-digit CODE-128 barcode when none was typed in."""
    if product.barcode:
        return
    candidate = f"890{product.pk:09d}"
    while Product.objects.filter(barcode=candidate).exclude(pk=product.pk).exists():
        candidate = f"890{uuid.uuid4().int % 10**9:09d}"
    # .update() so this housekeeping step doesn't create a second audit entry
    Product.objects.filter(pk=product.pk).update(barcode=candidate)
    product.barcode = candidate


@login_required
def product_create(request):
    # Only Admin and Manager can add products
    if request.user.role not in MANAGER_ROLES:
        messages.error(request, "You don't have permission to add products.")
        return redirect('product_list')

    form = ProductForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        product = form.save()
        _assign_barcode_if_missing(product)
        if product.cost_price and product.cost_price >= product.price:
            messages.warning(request, "Cost price is not lower than the selling price: this product has no margin.")
        messages.success(request, f"Product '{product.name}' added successfully.")
        return redirect('product_detail', pk=product.pk)

    return render(request, 'inventory/product_form.html', {'form': form, 'title': 'Add Product'})


@login_required
def product_update(request, pk):
    if request.user.role not in MANAGER_ROLES:
        messages.error(request, "You don't have permission to edit products.")
        return redirect('product_list')

    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, instance=product)
    if request.method == 'POST' and form.is_valid():
        product = form.save()
        _assign_barcode_if_missing(product)
        messages.success(request, f"Product '{product.name}' updated.")
        return redirect('product_detail', pk=product.pk)

    return render(request, 'inventory/product_form.html', {
        'form': form, 'title': f'Edit {product.name}', 'product': product,
    })


# --------------------------------------------------------------------------- categories

@login_required
def category_list(request):
    categories = Category.objects.annotate(product_count=Count('products')).order_by('name')
    return render(request, 'inventory/category_list.html', {
        'categories': categories,
        'can_edit': request.user.role in MANAGER_ROLES,
    })


@login_required
def category_create(request):
    if request.user.role not in MANAGER_ROLES:
        messages.error(request, "You don't have permission to add categories.")
        return redirect('category_list')

    form = CategoryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Category added.")
        return redirect('category_list')
    return render(request, 'inventory/category_form.html', {'form': form, 'title': 'Add Category'})


@login_required
def category_update(request, pk):
    if request.user.role not in MANAGER_ROLES:
        messages.error(request, "You don't have permission to edit categories.")
        return redirect('category_list')

    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Category updated.")
        return redirect('category_list')
    return render(request, 'inventory/category_form.html', {'form': form, 'title': f'Edit {category.name}'})


# --------------------------------------------------------------------------- stock movements

@login_required
def stock_movement_create(request):
    products = Product.objects.all().order_by('name')

    if request.method == 'POST':
        product = get_object_or_404(Product, pk=request.POST.get('product'))
        movement_type = request.POST.get('movement_type')

        try:
            quantity = int(request.POST.get('quantity', ''))
        except ValueError:
            quantity = 0
        if quantity < 1 or movement_type not in ('IN', 'OUT'):
            messages.error(request, "Enter a valid movement type and a quantity of at least 1.")
            return redirect('stock_movement_create')

        if movement_type == 'OUT' and quantity > product.quantity:
            messages.error(request, f"Cannot remove {quantity} units: only {product.quantity} in stock.")
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


# --------------------------------------------------------------------------- barcodes

@login_required
def barcode_image(request, pk):
    """Server-side PNG of the CODE-128 barcode (python-barcode). Used for downloads."""
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


@login_required
def barcode_lookup(request):
    code = request.GET.get('code', '').strip()
    try:
        product = Product.objects.get(barcode=code)
        return JsonResponse({
            'found': True, 'product_id': product.id, 'name': product.name,
            'price': float(product.price), 'stock': product.quantity,
        })
    except Product.DoesNotExist:
        return JsonResponse({'found': False})


# --------------------------------------------------------------------------- purchase orders

@login_required
def purchase_order_list(request):
    if request.user.role not in MANAGER_ROLES:
        messages.error(request, "You don't have permission to view purchase orders.")
        return redirect('dashboard')

    orders = PurchaseOrder.objects.select_related('supplier').all().order_by('-order_date')
    status = request.GET.get('status', '')
    if status:
        orders = orders.filter(status=status)
    return render(request, 'inventory/purchase_order_list.html', {
        'orders': orders,
        'status': status,
        'status_choices': PurchaseOrder.Status.choices,
    })


@login_required
def purchase_order_detail(request, pk):
    if request.user.role not in MANAGER_ROLES:
        messages.error(request, "You don't have permission to view purchase orders.")
        return redirect('dashboard')

    order = get_object_or_404(PurchaseOrder, pk=pk)
    return render(request, 'inventory/purchase_order_detail.html', {'order': order})


def send_po_email_to_supplier(order, triggered_by=None):
    if not order.supplier.email:
        return False
    items_text = "\n".join(
        f"- {item.product.name}: {item.quantity_ordered} units @ \u20b9{item.unit_cost} each"
        for item in order.items.all()
    )
    return dispatch_email(
        subject=f"New Purchase Order: {order.order_number}",
        body=(
            f"Dear {order.supplier.contact_person or order.supplier.name},\n\n"
            f"We would like to place the following order:\n\n"
            f"{items_text}\n\n"
            f"Grand Total: \u20b9{order.grand_total}\n"
            f"Requested Delivery Date: {order.expected_delivery_date or 'Not specified'}\n"
            f"Delivery Address: {order.delivery_address or 'Not specified'}\n"
            f"Payment Terms: {order.payment_terms}\n\n"
            f"Please confirm receipt and expected delivery date.\n\n"
            f"Regards,\nStockMS"
        ),
        recipients=[order.supplier.email],
        alert_type=EmailLog.AlertType.PURCHASE_CONFIRMATION,
        triggered_by=triggered_by,
    )


@login_required
def purchase_order_create(request):
    if request.user.role not in MANAGER_ROLES:
        messages.error(request, "You don't have permission to create purchase orders.")
        return redirect('dashboard')

    suppliers = Supplier.objects.all().order_by('name')
    products = Product.objects.select_related('supplier').all().order_by('name')

    if request.method == 'POST':
        supplier = get_object_or_404(Supplier, pk=request.POST.get('supplier'))

        # Collect valid item rows first so we never create an empty order
        rows = []
        for prod_id, qty, cost in zip(
            request.POST.getlist('product'),
            request.POST.getlist('quantity'),
            request.POST.getlist('unit_cost'),
        ):
            if prod_id and qty and cost:
                try:
                    rows.append((int(prod_id), int(qty), float(cost)))
                except ValueError:
                    continue
        rows = [r for r in rows if r[1] > 0 and r[2] >= 0]

        if not rows:
            messages.error(request, "Add at least one item with a quantity and unit cost.")
            return redirect('purchase_order_create')

        try:
            tax_percent = float(request.POST.get('tax_percent') or 0)
            discount = float(request.POST.get('discount_amount') or 0)
        except ValueError:
            messages.error(request, "Tax and discount must be numbers.")
            return redirect('purchase_order_create')

        margin_warnings = []
        with transaction.atomic():
            order = PurchaseOrder.objects.create(
                order_number=f"PO-{timezone.now().year}-{uuid.uuid4().hex[:6].upper()}",
                supplier=supplier,
                created_by=request.user,
                expected_delivery_date=request.POST.get('expected_delivery_date') or None,
                payment_terms=request.POST.get('payment_terms', 'Due on delivery'),
                delivery_address=request.POST.get('delivery_address', ''),
                tax_percent=tax_percent,
                discount_amount=discount,
                notes=request.POST.get('notes', ''),
            )
            for prod_id, qty, unit_cost in rows:
                product = Product.objects.get(pk=prod_id)
                if unit_cost >= float(product.price):
                    margin_warnings.append(
                        f"{product.name}: cost (\u20b9{unit_cost}) is not lower than selling price (\u20b9{product.price})."
                    )
                PurchaseOrderItem.objects.create(
                    purchase_order=order, product=product,
                    quantity_ordered=qty, unit_cost=unit_cost,
                )

        for warning in margin_warnings:
            messages.warning(request, warning)
        emailed = send_po_email_to_supplier(order, triggered_by=request.user)
        if emailed:
            messages.success(request, f"Purchase order {order.order_number} created and emailed to supplier.")
        else:
            messages.success(
                request,
                f"Purchase order {order.order_number} created. (No e-mail sent: supplier has no address or mail failed.)",
            )
        return redirect('purchase_order_detail', pk=order.pk)

    # Optional prefill, e.g. from the forecasting page: ?product=<id>&qty=<n>
    prefill = None
    prefill_id = request.GET.get('product', '')
    if prefill_id.isdigit():
        prefill_product = products.filter(pk=int(prefill_id)).first()
        if prefill_product:
            try:
                prefill_qty = max(int(request.GET.get('qty', prefill_product.suggested_reorder_quantity)), 1)
            except ValueError:
                prefill_qty = max(prefill_product.suggested_reorder_quantity, 1)
            prefill = {
                'product': prefill_product,
                'quantity': prefill_qty,
                'unit_cost': prefill_product.cost_price or '',
                'supplier_id': prefill_product.supplier_id,
            }

    return render(request, 'inventory/purchase_order_form.html', {
        'suppliers': suppliers,
        'products': products,
        'prefill': prefill,
    })


@login_required
def purchase_order_confirm_delivery(request, pk):
    if request.user.role not in MANAGER_ROLES:
        messages.error(request, "You don't have permission to do this.")
        return redirect('purchase_order_detail', pk=pk)

    order = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == 'POST':
        order.confirmed_delivery_date = request.POST.get('confirmed_delivery_date') or None
        order.save()
        messages.success(request, "Confirmed delivery date recorded.")
    return redirect('purchase_order_detail', pk=pk)


def send_discrepancy_email(order, receipt, triggered_by=None):
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
        dispatch_email(
            subject=f"Discrepancy in Delivery for {order.order_number}",
            body=(
                f"Dear {order.supplier.contact_person or order.supplier.name},\n\n"
                f"We received the delivery for order {order.order_number}, but found the following issues:\n\n"
                + "\n".join(problems) +
                "\n\nPlease advise on replacement or credit for the affected items.\n\nRegards,\nStockMS"
            ),
            recipients=[order.supplier.email],
            alert_type=EmailLog.AlertType.DELIVERY_DISCREPANCY,
            triggered_by=triggered_by,
        )


@login_required
def purchase_order_receive(request, pk):
    if request.user.role not in MANAGER_ROLES:
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

                    # Only usable goods are added to sellable stock
                    if receipt_item.usable_quantity > 0:
                        StockMovement.objects.create(
                            product=item.product,
                            movement_type='IN',
                            quantity=receipt_item.usable_quantity,
                            performed_by=request.user,
                            note=f"Received from {order.order_number} (Receipt #{receipt.id})",
                        )

                        # Resolve the stock alert once the product is back above its reorder level
                        product = item.product
                        if not product.is_low_stock:
                            StockAlert.objects.filter(product=product, resolved=False).update(
                                resolved=True, resolved_at=timezone.now()
                            )

                if not item.is_fully_received:
                    all_fully_received = False

            order.status = (
                PurchaseOrder.Status.RECEIVED if all_fully_received
                else PurchaseOrder.Status.PARTIALLY_RECEIVED
            )
            order.save()

        # Tell the supplier about shortfalls / damaged goods
        send_discrepancy_email(order, receipt, triggered_by=request.user)

        messages.success(request, f"Goods receipt recorded for {order.order_number}.")
        return redirect('purchase_order_detail', pk=pk)

    return render(request, 'inventory/goods_receipt_form.html', {'order': order})


@login_required
def purchase_order_cancel(request, pk):
    if request.user.role not in MANAGER_ROLES:
        messages.error(request, "You don't have permission to cancel purchase orders.")
        return redirect('purchase_order_list')

    order = get_object_or_404(PurchaseOrder, pk=pk)
    if order.status == 'PENDING':
        order.status = 'CANCELLED'
        order.save()
        messages.success(request, f"Order {order.order_number} cancelled.")
    return redirect('purchase_order_detail', pk=pk)


# --------------------------------------------------------------------------- suppliers

@login_required
def supplier_list(request):
    suppliers = Supplier.objects.annotate(product_count=Count('products')).order_by('name')
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
    if request.user.role not in MANAGER_ROLES:
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


# --------------------------------------------------------------------------- reports

@login_required
def reports_page(request):
    if request.user.role not in MANAGER_ROLES:
        messages.error(request, "You don't have permission to view reports.")
        return redirect('dashboard')

    products = list(Product.objects.select_related('category', 'supplier').order_by('name'))
    retail_value = sum(p.stock_value for p in products)
    cost_value = sum(p.stock_cost_value for p in products)
    low_stock_products = [p for p in products if p.is_low_stock]

    monthly = analytics.monthly_sales(6)
    totals = analytics.sales_totals()
    by_category = analytics.sales_by_category()

    # Purchase history
    orders = list(
        PurchaseOrder.objects.select_related('supplier').prefetch_related('items')
        .order_by('-order_date')[:50]
    )
    supplier_spend = {}
    for order in orders:
        if order.status != 'CANCELLED':
            supplier_spend[order.supplier.name] = (
                supplier_spend.get(order.supplier.name, 0) + order.total_value_received
            )

    # Future demand
    forecasts = [f for f in sort_by_urgency(get_all_forecasts()) if f['status'] == 'OK']

    context = {
        'total_inventory_value': retail_value,
        'inventory_cost_value': cost_value,
        'potential_profit': retail_value - cost_value,
        'products': products,
        'low_stock_products': low_stock_products,
        'top_products': analytics.top_products(5),
        'monthly_sales': monthly,
        'totals': totals,
        'by_category': by_category,
        'by_payment': analytics.sales_by_payment_method(),
        'orders': orders,
        'procurement_spend': analytics.procurement_spend(),
        'supplier_spend': sorted(supplier_spend.items(), key=lambda kv: -kv[1]),
        'forecasts': forecasts,
        'recent_emails': EmailLog.objects.select_related('product')[:25],
        'chart_data': {
            'monthly': {
                'labels': [m['label'] for m in monthly],
                'revenue': [float(m['revenue']) for m in monthly],
                'profit': [float(m['profit']) for m in monthly],
                'units': [m['units'] for m in monthly],
            },
            'category': {
                'labels': [c['product__category__name'] or 'Uncategorised' for c in by_category],
                'values': [float(c['revenue']) for c in by_category],
            },
        },
    }
    return render(request, 'inventory/reports.html', context)
