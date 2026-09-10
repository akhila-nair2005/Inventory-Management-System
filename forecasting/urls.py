from django.urls import path
from . import views

urlpatterns = [
    path('', views.forecast_page, name='forecast_page'),
    path('api/<int:product_id>/', views.forecast_view, name='forecast'),
]