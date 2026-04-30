# signals.py
import logging
import secrets
import string
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.db import IntegrityError

logger = logging.getLogger(__name__)
User = get_user_model()


@receiver(post_save, sender=User)
def send_credentials_on_user_creation(sender, instance, created, **kwargs):
    """
    Отправляет учётные данные при создании нового пользователя.
    """
    if not created:
        return
    if not getattr(instance, 'email', None):
        return
    # Не отправляем для default_teacher и системных пользователей
    if instance.username == 'default_teacher':
        return

    from .utils.email_utils import send_user_credentials_email

    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    temp_password = ''.join(secrets.choice(alphabet) for _ in range(12))

    instance.set_password(temp_password)
    instance.save(update_fields=['password'])

    try:
        send_user_credentials_email(instance, temp_password, force_send_password=True)
        logger.info(f"Учётные данные отправлены пользователю {instance.username} ({instance.email})")
    except Exception as e:
        logger.error(
            f"Не удалось отправить email пользователю {instance.username} "
            f"({instance.email}): {e}"
        )


@receiver(post_save, sender=User)
def create_student_profile(sender, instance, created, **kwargs):
    """
    Автоматически создаёт StudentProfile при создании пользователя с ролью student.
    """
    from .models import CustomUser, StudentProfile

    if not created:
        return
    if instance.role != CustomUser.STUDENT:
        return

    try:
        StudentProfile.objects.create(user=instance)
        logger.debug(f"Создан StudentProfile для пользователя {instance.username}")
    except IntegrityError:
        logger.warning(
            f"StudentProfile для {instance.username} (ID: {instance.id}) "
            f"уже существует, пропуск создания"
        )
    except Exception as e:
        logger.error(
            f"Неожиданная ошибка при создании StudentProfile "
            f"для {instance.username}: {e}"
        )