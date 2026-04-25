import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "mini-ups-dev-secret-key")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",") if host.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.interop",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "MiniUPS.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

WSGI_APPLICATION = "MiniUPS.wsgi.application"
ASGI_APPLICATION = "MiniUPS.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "postgres"),
        "USER": os.getenv("POSTGRES_USER", "postgres"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "postgres"),
        "HOST": os.getenv("POSTGRES_HOST", "db"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}

# Lab / dev: no password complexity validators (any password allowed).
AUTH_PASSWORD_VALIDATORS = []

AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.EmailOrUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TZ", "UTC")
USE_I18N = False
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "auth.User"
LOGIN_REDIRECT_URL = "my-packages"
LOGOUT_REDIRECT_URL = "home"

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "ups_sessionid")
CSRF_COOKIE_NAME = os.getenv("CSRF_COOKIE_NAME", "ups_csrftoken")

INTEROP_SHARED_SECRET = os.getenv("INTEROP_SHARED_SECRET", "mini-ups-shared-secret")
AMAZON_BASE_URL = os.getenv("AMAZON_BASE_URL", "").rstrip("/")
AMAZON_INTEROP_SECRET = os.getenv("AMAZON_INTEROP_SECRET", "").strip()
WORLD_HOST = os.getenv("WORLD_HOST", "host.docker.internal")
WORLD_PORT = int(os.getenv("WORLD_PORT", "12345"))
WORLD_ID = os.getenv("WORLD_ID", "")
WORLD_RETRY_SECONDS = int(os.getenv("WORLD_RETRY_SECONDS", "5"))
OUTBOUND_RETRY_SECONDS = int(os.getenv("OUTBOUND_RETRY_SECONDS", "5"))

DEFAULT_CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
    "http://*.vm.duke.edu:8000",
    "http://*.vm.duke.edu:8001",
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        ",".join(DEFAULT_CSRF_TRUSTED_ORIGINS),
    ).split(",")
    if origin.strip()
]

# email settings
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

EMAIL_HOST = 'smtp.qq.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True

EMAIL_HOST_USER = '1228280263@qq.com'
EMAIL_HOST_PASSWORD = 'qnsrhbheepbabagc'

DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
