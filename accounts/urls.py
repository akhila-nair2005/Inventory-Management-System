from django.urls import path
from . import views



urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('login/', views.RoleBasedLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
]