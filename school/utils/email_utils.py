# school/utils/email_utils.py
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def send_user_credentials_email(user, password=None, force_send_password=False):
    """
    Sends email with login and password to user
    
    Args:
        user: CustomUser object
        password: temporary password
        force_send_password: force send password in email
    """
    # Check email availability
    if not user.email:
        logger.warning(f"Cannot send credentials email: User {user.username} has no email address.")
        return False

    try:
        # Define user role in English
        role_names = {
            'teacher': 'Teacher',
            'student': 'Student',
            'tutor': 'Tutor',
            'scheduler': 'Schedule Manager'
        }
        
        role_display = role_names.get(user.role, user.role.capitalize())
        
        # Context for email template
        context = {
            'user': user,
            'username': user.username,
            'password': password if (password and force_send_password) else None,
            'role': role_display,
            'site_name': getattr(settings, 'SITE_NAME', 'Education Management System'),
            'login_url': getattr(settings, 'LOGIN_URL', '/login/'),
            'show_password': bool(password and force_send_password),
        }
        
        # Create email subject
        subject = f'Login Credentials - {role_display}'
        
        # Render HTML and text templates
        # Add try-except for template rendering
        try:
            html_message = render_to_string('emails/user_credentials.html', context)
            plain_message = render_to_string('emails/user_credentials.txt', context)
        except Exception as tmpl_e:
            logger.error(f"Failed to render email templates for user {user.username} ({user.email}): {str(tmpl_e)}")
            # Try to send simple text message
            plain_message = f"""
            Hello, {user.get_full_name() or user.username}!

            An account has been created for you in the "{getattr(settings, 'SITE_NAME', 'Education Management System')}" system with role: {role_display}

            Your login credentials:
            Username: {user.username}
            """
            if password and force_send_password:
                plain_message += f"Password: {password}\n\n"
                plain_message += "IMPORTANT: Save this password in a secure place and change it on first login.\n"
            else:
                plain_message += "Password was set previously. If you don't remember it, contact administrator for reset.\n"
            
            plain_message += f"\nLogin link: {getattr(settings, 'LOGIN_URL', '/login/')}\n\n"
            plain_message += "Best regards,\nSystem Administration"
            html_message = None # Don't send HTML if template doesn't render

        logger.debug(f"Sending email to {user.email} with subject '{subject}'")
        logger.debug(f"Plain message: {plain_message}")
        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message, # Can be None
            fail_silently=False
        )
        
        logger.info(f"Credentials email sent successfully to {user.email} for user {user.username}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send credentials email to {user.email} for user {user.username}: {str(e)}", exc_info=True) # exc_info=True for full traceback
        return False


def send_password_reset_email(user, new_password):
    """
    Sends email with new password to user
    
    Args:
        user: CustomUser object
        new_password: new password
    """
    # Check email availability
    if not user.email:
        logger.warning(f"Cannot send password reset email: User {user.username} has no email address.")
        return False

    try:
        # Define user role in English
        role_names = {
            'teacher': 'Teacher',
            'student': 'Student',
            'tutor': 'Tutor',
            'scheduler': 'Schedule Manager'
        }
        
        role_display = role_names.get(user.role, user.role.capitalize())
        
        # Context for email template
        context = {
            'user': user,
            'username': user.username,
            'new_password': new_password,
            'role': role_display,
            'site_name': getattr(settings, 'SITE_NAME', 'Education Management System'),
            'login_url': getattr(settings, 'LOGIN_URL', '/login/'),
        }
        
        # Create email subject
        subject = f'New Password for System Login - {role_display}'
        
        # Render HTML and text templates
        try:
            html_message = render_to_string('emails/password_reset.html', context)
            plain_message = render_to_string('emails/password_reset.txt', context)
        except Exception as tmpl_e:
            logger.error(f"Failed to render password reset email templates for user {user.username} ({user.email}): {str(tmpl_e)}")
            # Simple text message
            plain_message = f"""
            Hello, {user.get_full_name() or user.username}!

            Your password in the "{getattr(settings, 'SITE_NAME', 'Education Management System')}" system has been reset.

            Your new login credentials:
            Username: {user.username}
            New Password: {new_password}

            IMPORTANT: Save this password in a secure place and change it on first login.
            
            Login link: {getattr(settings, 'LOGIN_URL', '/login/')}

            Best regards,
            System Administration
            """
            html_message = None

        logger.debug(f"Sending password reset email to {user.email} with subject '{subject}'")
        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False
        )
        
        logger.info(f"Password reset email sent successfully to {user.email} for user {user.username}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send password reset email to {user.email} for user {user.username}: {str(e)}", exc_info=True)
        return False