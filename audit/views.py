from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import AuditLog


@login_required
def audit_log_list(request):
    if request.user.role != 'ADMIN':
        messages.error(request, "You don't have permission to view audit logs.")
        return redirect('dashboard')

    logs = AuditLog.objects.select_related('user').all()

    # Optional filtering
    action_filter = request.GET.get('action')
    model_filter = request.GET.get('model')

    if action_filter:
        logs = logs.filter(action=action_filter)
    if model_filter:
        logs = logs.filter(model_name=model_filter)

    logs = logs[:200]  # cap for performance/demo clarity

    return render(request, 'audit/audit_log_list.html', {
        'logs': logs,
        'action_filter': action_filter,
        'model_filter': model_filter,
    })