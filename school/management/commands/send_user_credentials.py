# school/management/commands/send_user_credentials.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import secrets
import string

User = get_user_model()

class Command(BaseCommand):
    help = 'Отправляет учетные данные пользователям по email (по умолчанию только студентам)'

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int, help='ID пользователя')
        parser.add_argument('--username', type=str, help='Username пользователя')
        parser.add_argument('--all-users', action='store_true', help='Отправить всем пользователям (с фильтром по роли, если не указано --role)')
        parser.add_argument('--role', type=str, help='Роль пользователей (например, student, teacher). По умолчанию student.')
        parser.add_argument('--generate-password', action='store_true', help='Сгенерировать новый пароль')
        parser.add_argument('--force-send-password', action='store_true', help='Принудительно отправить пароль')

    def handle(self, *args, **options):
        # Определяем роль: по умолчанию 'student', если не указана другая или не запрошены все пользователи без фильтра
        if options['role']:
            role = options['role']
        elif options['all_users']:
            # Если --all-users указан без --role, отправляем всем, но с фильтром по email
            role = None
        else:
            # По умолчанию для отдельных пользователей или --all-users без --role отправляем студентам
            role = 'student' # Используем строковое значение, соответствующее CustomUser.STUDENT

        # Получаем QuerySet пользователей
        user_qs = User.objects.all()
        
        # Применяем фильтр по роли, если она указана или используется значение по умолчанию 'student'
        if role:
            user_qs = user_qs.filter(role=role)
            self.stdout.write(f"[INFO] Фильтрация по роли: {role}")
        else:
            self.stdout.write("[INFO] Роль не указана, фильтрация только по наличию email.")

        # Фильтруем по наличию email
        user_qs = user_qs.filter(email__isnull=False).exclude(email='')

        if options['user_id']:
            try:
                user = user_qs.get(id=options['user_id'])
                self.send_credentials_to_user(user, options['generate_password'], options['force_send_password'])
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Пользователь с ID {options["user_id"]} (роль: {role or "любая"}) не найден'))
                
        elif options['username']:
            try:
                user = user_qs.get(username=options['username'])
                self.send_credentials_to_user(user, options['generate_password'], options['force_send_password'])
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Пользователь {options["username"]} (роль: {role or "любая"}) не найден'))
                
        elif options['all_users']:
            count = user_qs.count()
            self.stdout.write(f"[INFO] Найдено пользователей для отправки: {count}")
            for user in user_qs:
                self.send_credentials_to_user(user, options['generate_password'], options['force_send_password'])
            self.stdout.write(self.style.SUCCESS(f'Завершено. Обработано пользователей: {count}'))
        else:
            self.stdout.write(self.style.ERROR('Укажите --user-id, --username или --all-users'))

    def send_credentials_to_user(self, user, generate_password, force_send):
        # Импортируем здесь, чтобы избежать циклических импортов
        from school.utils.email_utils import send_user_credentials_email
        
        if not user.email:
            # Дополнительная проверка на всякий случай
            self.stdout.write(self.style.WARNING(f'У пользователя {user.username} нет email (ID: {user.id})'))
            return
            
        password = None
        # Генерируем новый пароль, если явно указано или у пользователя нет usable password
        if generate_password or not user.has_usable_password():
            alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
            password = ''.join(secrets.choice(alphabet) for _ in range(12))
            user.set_password(password)
            user.save(update_fields=['password'])
            self.stdout.write(f"[DEBUG] Сгенерирован новый пароль для пользователя {user.username}")
            
        # Отправляем email
        success = send_user_credentials_email(user, password, force_send_password=force_send or bool(password))
        if success:
            action = "с новым паролем" if (force_send or bool(password)) else "с напоминанием"
            self.stdout.write(self.style.SUCCESS(f'Email {action} отправлен: {user.username} ({user.email}, роль: {getattr(user, "role", "N/A")})'))
        else:
            self.stdout.write(self.style.ERROR(f'Ошибка отправки email: {user.username} ({user.email})'))
