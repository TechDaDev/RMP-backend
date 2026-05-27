from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .services import get_or_create_wallet


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_wallet(sender, instance, created, **kwargs):
    if created:
        get_or_create_wallet(instance)
