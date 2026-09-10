from django.shortcuts import render

# Create your views here.
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from inventory.models import Product
from .forecasting_utils import moving_average_forecast, linear_regression_forecast


def forecast_view(request, product_id):
    """JSON API endpoint - unchanged"""
    product = get_object_or_404(Product, id=product_id)
    method = request.GET.get('method', 'linear')

    if method == 'moving_average':
        result = moving_average_forecast(product_id)
    else:
        result = linear_regression_forecast(product_id)

    result['product'] = product.name
    return JsonResponse(result)


@login_required
def forecast_page(request):
    """Frontend page with product selector and chart"""
    products = Product.objects.all()
    selected_product = None
    forecast_data = None

    product_id = request.GET.get('product')
    if product_id:
        selected_product = get_object_or_404(Product, id=product_id)
        ma_result = moving_average_forecast(product_id)
        lr_result = linear_regression_forecast(product_id)
        forecast_data = {
            'moving_average': ma_result,
            'linear_regression': lr_result,
        }

    return render(request, 'forecasting/forecast_page.html', {
        'products': products,
        'selected_product': selected_product,
        'forecast_data': forecast_data,
    })