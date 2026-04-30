from django.apps import AppConfig

class SchoolConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'school'

    def ready(self):
        from django.db.models.signals import post_save
        from .models import CustomUser
        from .signals import send_credentials_on_user_creation
        
        # Подключаем сигнал только к модели CustomUser
        post_save.connect(
            send_credentials_on_user_creation,
            sender=CustomUser,
            dispatch_uid='send_credentials_customuser'  # Уникальный ID для предотвращения дублирования
        )