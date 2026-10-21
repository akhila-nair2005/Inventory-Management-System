from django.urls import path
from . import views

urlpatterns = [
    path('', views.product_list, name='product_list'),
    path('add/', views.product_create, name='product_create'),
    path('<int:pk>/', views.product_detail, name='product_detail'),
    path('<int:pk>/edit/', views.product_update, name='product_update'),
    path('movement/add/', views.stock_movement_create, name='stock_movement_create'),
    path('<int:pk>/barcode/', views.barcode_image, name='barcode_image'),
    path('barcode/lookup/', views.barcode_lookup, name='barcode_lookup'),

    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_update, name='category_update'),

    path('purchase-orders/', views.purchase_order_list, name='purchase_order_list'),
    path('purchase-orders/add/', views.purchase_order_create, name='purchase_order_create'),
    path('purchase-orders/<int:pk>/', views.purchase_order_detail, name='purchase_order_detail'),
    path('purchase-orders/<int:pk>/receive/', views.purchase_order_receive, name='purchase_order_receive'),
    path('purchase-orders/<int:pk>/cancel/', views.purchase_order_cancel, name='purchase_order_cancel'),
    path('purchase-orders/<int:pk>/confirm-delivery/', views.purchase_order_confirm_delivery, name='confirm_delivery'),

    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/add/', views.supplier_create, name='supplier_create'),
    path('suppliers/<int:pk>/', views.supplier_detail, name='supplier_detail'),

    path('reports/', views.reports_page, name='reports_page'),
]
