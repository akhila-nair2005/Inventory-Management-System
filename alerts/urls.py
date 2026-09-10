from django.urls import path
from . import views

urlpatterns = [
    path('', views.alert_list, name='alert_list'),
    path('<int:pk>/resolve/', views.resolve_alert, name='resolve_alert'),
]