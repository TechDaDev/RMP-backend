from decouple import config

from .base import *  # noqa: F401,F403


DEBUG = config("DEBUG", cast=bool, default=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="alrafidain_db"),
        "USER": config("DB_USER", default="alrafidain_user"),
        "PASSWORD": config("DB_PASSWORD", default="alrafidain_password"),
        "HOST": config("DB_HOST", default="127.0.0.1"),
        "PORT": config("DB_PORT", default="5432"),
    }
}