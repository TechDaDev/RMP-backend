from pathlib import Path

from decouple import Csv, config


BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("SECRET_KEY", default="change-me")
DEBUG = config("DEBUG", cast=bool, default=False)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv(), default="127.0.0.1,localhost")

INSTALLED_APPS = [
    "daphne",
    "django_cleanup.apps.CleanupConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "django_filters",
    "corsheaders",
    "django_extensions",
    "channels",
    "apps.common",
    "apps.accounts.apps.AccountsConfig",
    "apps.profiles.apps.ProfilesConfig",
    "apps.audit.apps.AuditConfig",
    "apps.consultations.apps.ConsultationsConfig",
    "apps.messaging.apps.MessagingConfig",
    "apps.prescriptions.apps.PrescriptionsConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.patient_records.apps.PatientRecordsConfig",
    "apps.lab_orders.apps.LabOrdersConfig",
    "apps.knowledge_base.apps.KnowledgeBaseConfig",
    "apps.rag.apps.RagConfig",
    "apps.realtime.apps.RealtimeConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Baghdad"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
    ),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "login": "10/minute",
        "otp": "5/minute",
        "qr_scan": "30/minute",
        "password_reset": "5/minute",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Al-Rafidain Medical Platform API",
    "DESCRIPTION": "Backend API for Al-Rafidain Medical Platform.",
    "VERSION": "0.1.0",
}

CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    cast=Csv(),
    default="http://localhost:3000,http://127.0.0.1:3000",
)

AUTH_USER_MODEL = "accounts.User"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "noreply@alrafidain.local"

# ── Embedding settings ──────────────────────────────────────────────────────
EMBEDDING_MODEL_NAME = config(
    "EMBEDDING_MODEL_NAME",
    default="sentence-transformers/all-MiniLM-L6-v2",
)
EMBEDDING_VECTOR_DIMENSION = config(
    "EMBEDDING_VECTOR_DIMENSION",
    default=384,
    cast=int,
)

# ── DeepSeek / RAG settings ────────────────────────────────────────────
DEEPSEEK_API_KEY = config("DEEPSEEK_API_KEY", default="")
DEEPSEEK_BASE_URL = config("DEEPSEEK_BASE_URL", default="https://api.deepseek.com")
DEEPSEEK_MODEL = config("DEEPSEEK_MODEL", default="deepseek-chat")
DEEPSEEK_TIMEOUT_SECONDS = config("DEEPSEEK_TIMEOUT_SECONDS", default=60, cast=int)

RAG_DEFAULT_TOP_K = config("RAG_DEFAULT_TOP_K", default=6, cast=int)
RAG_MAX_TOP_K = config("RAG_MAX_TOP_K", default=12, cast=int)

# ── Phase 12E — Dataset export salt ────────────────────────────────────
# Used to hash doctor/object IDs in exported datasets.
# Set to a secret value in production. Falls back to SECRET_KEY if unset.
EXPORT_HASH_SALT = config("EXPORT_HASH_SALT", default=SECRET_KEY)

# ── Phase 14 — Django Channels & WebSocket ─────────────────────────────────
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                (
                    config("REDIS_HOST", default="127.0.0.1"),
                    config("REDIS_PORT", default=6379, cast=int),
                )
            ],
        },
    },
}
