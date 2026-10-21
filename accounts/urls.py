from django.urls import path
from . import views


urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('login/', views.RoleBasedLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Staff management (Admin only)
    path('staff/', views.staff_list, name='staff_list'),
    path('staff/add/', views.staff_create, name='staff_create'),
    path('staff/<int:pk>/edit/', views.staff_update, name='staff_update'),
    path('staff/<int:pk>/toggle/', views.staff_toggle_active, name='staff_toggle_active'),
]
