# school/permissions.py или добавить в конец models.py
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from .models import CustomUser, StudentProfile, Group # Импортируйте нужные модели

def create_tutor_permissions():
    """Создает кастомные разрешения для роли тьютора, если они не существуют."""
    # Для CustomUser (если нужно управлять студентами как пользователями)
    user_ct = ContentType.objects.get_for_model(CustomUser)
    Permission.objects.get_or_create(
        codename='can_manage_students_as_user',
        name='Can Manage Students (User Level)',
        content_type=user_ct,
    )

    # Для StudentProfile
    student_ct = ContentType.objects.get_for_model(StudentProfile)
    Permission.objects.get_or_create(
        codename='can_add_studentprofile',
        name='Can Add Student Profile',
        content_type=student_ct,
    )
    Permission.objects.get_or_create(
        codename='can_change_studentprofile',
        name='Can Change Student Profile',
        content_type=student_ct,
    )
    Permission.objects.get_or_create(
        codename='can_view_studentprofile',
        name='Can View Student Profile',
        content_type=student_ct,
    )
    # Умышленно НЕ создаем can_delete_studentprofile для этой роли

    # Для Group
    group_ct = ContentType.objects.get_for_model(Group)
    Permission.objects.get_or_create(
        codename='can_add_group',
        name='Can Add Group',
        content_type=group_ct,
    )
    Permission.objects.get_or_create(
        codename='can_change_group',
        name='Can Change Group',
        content_type=group_ct,
    )
    Permission.objects.get_or_create(
        codename='can_view_group',
        name='Can View Group',
        content_type=group_ct,
    )
