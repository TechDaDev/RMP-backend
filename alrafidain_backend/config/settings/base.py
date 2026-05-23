from datetime import timedelta
from pathlib import Path

from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

ENVIRONMENT = config("ENVIRONMENT", default="local")

_ALLOWED_ENVIRONMENTS = {"local", "test", "staging", "production"}
if ENVIRONMENT not in _ALLOWED_ENVIRONMENTS:
    allowed = ", ".join(sorted(_ALLOWED_ENVIRONMENTS))
    raise ImproperlyConfigured(f"Invalid ENVIRONMENT '{ENVIRONMENT}'. Expected one of: {allowed}.")

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", cast=bool, default=False)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv(), default="127.0.0.1,localhost")

_normalized_secret = SECRET_KEY.strip().lower()
_weak_secret_values = {
    "",
    "change-me",
    "changeme",
    "secret",
    "dev-secret",
    "test-secret",
}

if ENVIRONMENT in {"production", "staging"} and (
    _normalized_secret in _weak_secret_values
    or _normalized_secret.startswith("django-insecure")
):
    raise ImproperlyConfigured(
        "SECRET_KEY is weak for staging/production. Please set a strong secret."
    )

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
    "apps.common.middleware.RequestIDMiddleware",
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

REDIS_URL = config(
    "REDIS_URL",
    default=(
        f"redis://{config('REDIS_HOST', default='127.0.0.1')}:"
        f"{config('REDIS_PORT', default=6379, cast=int)}/0"
    ),
)

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

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
CELERY_TIMEZONE = TIME_ZONE

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

MAX_KNOWLEDGE_DOCUMENT_UPLOAD_MB = config("MAX_KNOWLEDGE_DOCUMENT_UPLOAD_MB", default=20, cast=int)
MAX_CLINICAL_ATTACHMENT_UPLOAD_MB = config(
    "MAX_CLINICAL_ATTACHMENT_UPLOAD_MB", default=15, cast=int
)
MAX_PROFILE_IMAGE_UPLOAD_MB = config("MAX_PROFILE_IMAGE_UPLOAD_MB", default=5, cast=int)

KNOWLEDGE_DOCUMENT_ALLOWED_EXTENSIONS = [".pdf", ".docx", ".txt"]
KNOWLEDGE_DOCUMENT_ALLOWED_CONTENT_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
]

CLINICAL_ATTACHMENT_ALLOWED_EXTENSIONS = [
    ".pdf",
    ".docx",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
]
CLINICAL_ATTACHMENT_ALLOWED_CONTENT_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "image/jpeg",
    "image/png",
    "image/webp",
]

PROFILE_IMAGE_ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]
PROFILE_IMAGE_ALLOWED_CONTENT_TYPES = ["image/jpeg", "image/png", "image/webp"]

FILE_SCANNING_ENABLED = config("FILE_SCANNING_ENABLED", default=False, cast=bool)
FILE_SCANNER_BACKEND = config("FILE_SCANNER_BACKEND", default="")
PRIVATE_MEDIA_STORAGE = config("PRIVATE_MEDIA_STORAGE", default=False, cast=bool)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler",
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

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=24),
}

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
DEEPSEEK_MODEL = config("DEEPSEEK_MODEL", default="deepseek-v4-flash")
DEEPSEEK_TIMEOUT_SECONDS = config("DEEPSEEK_TIMEOUT_SECONDS", default=60, cast=int)
CONSULTATION_TRIAGE_USE_LLM = config("CONSULTATION_TRIAGE_USE_LLM", default=True, cast=bool)
CONSULTATION_TRIAGE_MAX_SPECIALTIES = config(
    "CONSULTATION_TRIAGE_MAX_SPECIALTIES",
    default=3,
    cast=int,
)

RAG_DEFAULT_TOP_K = config("RAG_DEFAULT_TOP_K", default=6, cast=int)
RAG_MAX_TOP_K = config("RAG_MAX_TOP_K", default=12, cast=int)
RAG_MIN_CONFIDENCE = config("RAG_MIN_CONFIDENCE", default=0.45, cast=float)
RAG_REQUIRE_SOURCES = config("RAG_REQUIRE_SOURCES", default=True, cast=bool)
RAG_MAX_CONTEXT_CHUNKS = config("RAG_MAX_CONTEXT_CHUNKS", default=5, cast=int)
RAG_MAX_QUERY_LENGTH = config("RAG_MAX_QUERY_LENGTH", default=2000, cast=int)
RAG_MAX_ANSWER_LENGTH = config("RAG_MAX_ANSWER_LENGTH", default=4000, cast=int)
RAG_EXPORT_MAX_ROWS = config("RAG_EXPORT_MAX_ROWS", default=10000, cast=int)
RAG_MAX_REPORT_FILES = config("RAG_MAX_REPORT_FILES", default=3, cast=int)
RAG_REPORT_TEXT_CHARS_PER_FILE = config("RAG_REPORT_TEXT_CHARS_PER_FILE", default=1500, cast=int)

# OCR for clinical reports (attachments and uploaded result files)
OCR_LANGUAGES = config("OCR_LANGUAGES", cast=Csv(), default="ar,en,ku")
OCR_USE_GPU = config("OCR_USE_GPU", default=False, cast=bool)
OCR_MAX_EXTRACTED_CHARS = config("OCR_MAX_EXTRACTED_CHARS", default=6000, cast=int)
OCR_MIN_MEDICAL_TERM_HITS = config("OCR_MIN_MEDICAL_TERM_HITS", default=2, cast=int)
CLINICAL_REPORT_OCR_ON_UPLOAD = config("CLINICAL_REPORT_OCR_ON_UPLOAD", default=False, cast=bool)
CLINICAL_REPORT_OCR_SYNC_ON_UPLOAD = config(
    "CLINICAL_REPORT_OCR_SYNC_ON_UPLOAD", default=False, cast=bool
)
CLINICAL_REPORT_OCR_MAX_INLINE_MB = config(
    "CLINICAL_REPORT_OCR_MAX_INLINE_MB", default=5, cast=int
)
CLINICAL_REPORT_LLM_ENABLED = config("CLINICAL_REPORT_LLM_ENABLED", default=False, cast=bool)
CLINICAL_REPORT_LLM_SYNC_AFTER_OCR = config(
    "CLINICAL_REPORT_LLM_SYNC_AFTER_OCR", default=False, cast=bool
)
CLINICAL_REPORT_LLM_MODEL = config("CLINICAL_REPORT_LLM_MODEL", default=DEEPSEEK_MODEL)
CLINICAL_REPORT_LLM_MAX_INPUT_CHARS = config(
    "CLINICAL_REPORT_LLM_MAX_INPUT_CHARS", default=6000, cast=int
)
CLINICAL_REPORT_LLM_MAX_OUTPUT_CHARS = config(
    "CLINICAL_REPORT_LLM_MAX_OUTPUT_CHARS", default=4000, cast=int
)
CLINICAL_REPORT_LLM_MIN_CONFIDENCE = config(
    "CLINICAL_REPORT_LLM_MIN_CONFIDENCE", default=0.60, cast=float
)
CLINICAL_REPORT_LLM_TIMEOUT_SECONDS = config(
    "CLINICAL_REPORT_LLM_TIMEOUT_SECONDS", default=30, cast=int
)

# ── Phase 12E — Dataset export salt ────────────────────────────────────
# Used to hash doctor/object IDs in exported datasets.
# Set to a secret value in production.
EXPORT_HASH_SALT = config("EXPORT_HASH_SALT", default=None)

if ENVIRONMENT == "production" and not EXPORT_HASH_SALT:
    raise ImproperlyConfigured("EXPORT_HASH_SALT must be set in production.")

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

SENTRY_DSN = config("SENTRY_DSN", default="")
SENTRY_TRACES_SAMPLE_RATE = config("SENTRY_TRACES_SAMPLE_RATE", default=0.0, cast=float)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {
            "()": "apps.common.logging.RequestIDLogFilter",
        },
    },
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
        },
        "verbose": {
            "format": (
                "%(asctime)s %(levelname)s %(name)s %(filename)s:%(lineno)d "
                "request_id=%(request_id)s %(message)s"
            ),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "standard",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": config("LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": config("DJANGO_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": config("APP_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
    },
}
