"""
Django settings for school_project project.
"""

import os
from pathlib import Path
from celery.schedules import crontab

import environ



BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')
SECRET_KEY = env('SECRET_KEY')

DEBUG = env.bool('DEBUG', False)

ALLOWED_HOSTS = ['mbaasoiu.online', 'www.mbaasoiu.online', 'localhost', '127.0.0.1']

CSRF_TRUSTED_ORIGINS = [
    'https://mbaasoiu.online',
    'http://mbaasoiu.online',
    'http://127.0.0.1:8000',
    'http://localhost:8000',
    'https://prod-production-b21c.up.railway.app',
    'https://prod-production-85fc.up.railway.app'
]

# Custom User Model
AUTH_USER_MODEL = 'school.CustomUser'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_URL = '/login/'

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    'django.contrib.sites',
    'school',
    'django_celery_beat',
    'axes',
    'evaluation',
    'apps.analytics',
    'apps.backup',
    'apps.notifications',
]

SITE_ID = 1

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    'school.middleware.RequestLoggerMiddleware',
    'axes.middleware.AxesMiddleware',
    'evaluation.middleware.EvaluationRequiredMiddleware',
]

ROOT_URLCONF = "school_project.urls"

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Axes settings
AXES_LOCKOUT_PARAMETERS = ['ip_address']
AXES_FAILURE_LIMIT = 15
AXES_COOLOFF_TIME = 1
AXES_LOCKOUT_TEMPLATE = 'school/lockout.html'
AXES_RESET_ON_SUCCESS = True

SITE_NAME = 'STMS'
SITE_URL = 'https://mbaasoiu.online'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = "school_project.wsgi.application"

# Database
from decouple import config
import dj_database_url

# DATABASES = {
#     'default': dj_database_url.config(
#         default=config('DATABASE_URL'),
#         conn_max_age=600,
#     )
# }




DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'school-cache',
    }
}
CURRENT_SEMESTER_CACHE_TTL = 86400  # 24 hours

# Password validation
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

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Baku"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
if os.environ.get('RAILWAY_ENV'):
    MEDIA_ROOT = '/app/media'
else:
    MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email settings
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
ADMIN_EMAIL = env('ADMIN_EMAIL', default=EMAIL_HOST_USER)


# Celery Configuration
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Celery Beat Schedule
CELERY_BEAT_SCHEDULE = {
    'weekly-backup': {
        'task': 'apps.backup.tasks.create_weekly_backup',
        'schedule': crontab(day_of_week=0, hour=2, minute=0),
    },
    'cleanup-old-backups': {
        'task': 'apps.backup.tasks.cleanup_old_backups',
        'schedule': crontab(day_of_week=1, hour=3, minute=0),
    },
    'cleanup-old-logs': {
        'task': 'apps.backup.tasks.cleanup_old_logs',
        'schedule': crontab(hour=4, minute=0),
    },
}

# Directories
BACKUP_DIR = BASE_DIR / 'backups'
LOGGING_DIR = BASE_DIR / 'logs'

# Create directories if they don't exist
BACKUP_DIR.mkdir(exist_ok=True)
LOGGING_DIR.mkdir(exist_ok=True)

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {module} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{asctime} {levelname} {message}',
            'style': '{',
        },
    },

    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGGING_DIR / 'app.log',
            'maxBytes': 1024 * 1024 * 5,  # 5 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'WARNING',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },

    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        'school': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'school.tasks': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Security settings
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
