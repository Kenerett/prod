# school/utils/email_utils.py
# Backwards-compatible re-export from new location
from apps.notifications.utils import send_user_credentials_email, send_password_reset_email

__all__ = ['send_user_credentials_email', 'send_password_reset_email']
