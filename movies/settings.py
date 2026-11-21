"""
Django settings for movies project.
Local PostgreSQL is always used (set DATABASE_URL in .env).
DRF and CORS have been removed — this is a template-only Django app.
"""

from pathlib import Path
import os
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', '')
DEBUG      = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')

if not DEBUG and not SECRET_KEY:
    raise ImproperlyConfigured(
        'SECRET_KEY must be set in the environment when DEBUG is False.'
    )

# TMDB key — only used by management command, never during a user request
TMDB_API_KEY = os.environ.get('TMDB_API_KEY', '')

ALLOWED_HOSTS = [
    host.strip().replace('https://', '').replace('http://', '')
    for host in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if host.strip()
]

if not DEBUG and '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        'ALLOWED_HOSTS must not contain "*" when DEBUG is False.'
    )

# CSRF Trusted Origins (required for Django 4.0+ with custom domains)
CSRF_TRUSTED_ORIGINS = [
    f"https://{host}" for host in ALLOWED_HOSTS
    if host and host != '*' and '.' in host
]

# =============================================================================
# Application definition
# =============================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',
    'rest_framework',

    # Cloudinary (for media storage if deploying)
    'cloudinary_storage',
    'cloudinary',

    # Local apps
    'movie.apps.MovieConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'movies.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'Template')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'movies.wsgi.application'

# =============================================================================
# Database — PostgreSQL (required, set DATABASE_URL in .env)
# =============================================================================

import dj_database_url

_DATABASE_URL = os.environ.get('DATABASE_URL')

if _DATABASE_URL and _DATABASE_URL.startswith('postgres'):
    DATABASES = {
        'default': dj_database_url.parse(_DATABASE_URL)
    }
    DATABASES['default']['CONN_MAX_AGE'] = 600
    DATABASES['default']['CONN_HEALTH_CHECKS'] = True
else:
    # Fallback to SQLite only if DATABASE_URL is missing or local
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# =============================================================================
# Caching — simple in-memory cache (data is in DB, no need for file cache)
# =============================================================================

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'movie-cache',
    }
}

# =============================================================================
# Auth
# =============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# =============================================================================
# Internationalisation
# =============================================================================

LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'Asia/Kolkata'
USE_I18N      = True
USE_L10N      = True
USE_TZ        = True

# =============================================================================
# Static & Media files
# =============================================================================

STATIC_URL      = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT     = os.path.join(BASE_DIR, 'assets')

# Media & Storage settings for Django 4.2+ (Media on Cloudinary, Static on WhiteNoise)
MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage" if os.environ.get('CLOUDINARY_URL') else "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# =============================================================================
# Misc
# =============================================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
