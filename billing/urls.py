from django.urls import path
from . import views

urlpatterns = [
    path('', views.invoice_list, name='invoice_list'),
    path('add/', views.invoice_create, name='invoice_create'),
    path('<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('<int:pk>/mark-paid/', views.mark_invoice_paid, name='mark_invoice_paid'),

]