from django.conf import settings
from django.core.checks import Warning, register


@register()
def private_media_storage_check(app_configs, **kwargs):
    environment = getattr(settings, "ENVIRONMENT", "local")
    private_media = getattr(settings, "PRIVATE_MEDIA_STORAGE", False)

    if environment == "production" and not private_media:
        return [
            Warning(
                "PRIVATE_MEDIA_STORAGE is disabled in production.",
                hint=(
                    "Use private object storage and signed downloads for clinical deployments. "
                    "See docs/FILE_SECURITY.md for guidance."
                ),
                id="common.W001",
            )
        ]
    return []
    return []
