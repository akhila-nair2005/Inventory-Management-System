from django.db import models

# Create your models here.
from django.conf import settings


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = 'CREATE', 'Create'
        UPDATE = 'UPDATE', 'Update'
        DELETE = 'DELETE', 'Delete'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=10, choices=Action.choices)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=50)
    object_repr = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} - {self.model_name} #{self.object_id} by {self.user}"

    class Meta:
        ordering = ['-timestamp']