# school/forms.py

from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import CustomUser, Group, TeacherAssignment, Room, ScheduleEntry
# forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _  # <- Добавьте это
from .models import CustomUser


# forms.py

from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import CustomUser
import logging

logger = logging.getLogger(__name__)

class CustomUserCreationForm(UserCreationForm):
    # Явно добавляем поле email и делаем его обязательным
    email = forms.EmailField(required=True, label=_("Email"))
    
    # Добавляем дополнительные поля
    first_name = forms.CharField(max_length=50, required=True, label=_("First Name"))
    last_name = forms.CharField(max_length=50, required=True, label=_("Last Name"))
    middle_name = forms.CharField(max_length=50, required=False, label=_("Middle Name"))

    class Meta:
        model = CustomUser
        fields = ("username", "email", "first_name", "last_name", "middle_name", "role")

    def clean_email(self):
        """Проверка email на уникальность"""
        email = self.cleaned_data.get('email')
        if email and CustomUser.objects.filter(email=email).exists():
            raise ValidationError(_("Пользователь с таким email уже существует."))
        return email

    def clean_username(self):
        """Дополнительная проверка username"""
        username = self.cleaned_data.get('username')
        if not username:
            raise ValidationError(_("Username обязателен для заполнения."))
        if CustomUser.objects.filter(username=username).exists():
            raise ValidationError(_("Пользователь с таким username уже существует."))
        return username

    def save(self, commit=True):
        try:
            user = super().save(commit=False)
            user.email = self.cleaned_data["email"]
            user.first_name = self.cleaned_data["first_name"]
            user.last_name = self.cleaned_data["last_name"]
            user.middle_name = self.cleaned_data.get("middle_name", "")
            
            if commit:
                user.save()
                logger.info(f'Пользователь {user.username} успешно создан через форму')
            
            return user
        except Exception as e:
            logger.error(f'Ошибка при создании пользователя через форму: {str(e)}')
            raise ValidationError(f'Ошибка при создании пользователя: {str(e)}')


class CustomUserChangeForm(UserChangeForm):
    # Делаем email обязательным и добавляем валидацию
    email = forms.EmailField(required=True, label=_("Email"))

    # Поле для изменения пароля (необязательное)
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput,
        required=False,
        help_text=_("Оставьте пустым, чтобы сохранить текущий пароль")
    )

    class Meta:
        model = CustomUser
        fields = '__all__'

    def clean_email(self):
        """Проверка email на уникальность (игнорируя текущего пользователя)"""
        email = self.cleaned_data.get('email')
        if email and CustomUser.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError(_("Пользователь с таким email уже существует."))
        return email

    def save(self, commit=True):
        try:
            user = super().save(commit=False)
            user.email = self.cleaned_data["email"]
            
            # Устанавливаем новый пароль, если он был введен
            if self.cleaned_data.get("password"):
                user.set_password(self.cleaned_data["password"])
            
            if commit:
                user.save()
                logger.info(f'Пользователь {user.username} успешно обновлен через форму')
            
            return user
        except Exception as e:
            logger.error(f'Ошибка при обновлении пользователя {user.username}: {str(e)}')
            raise ValidationError(f'Ошибка при обновлении пользователя: {str(e)}')







# Форма для создания/редактирования записи в расписании
class ScheduleEntryForm(forms.ModelForm):
    class Meta:
        model = ScheduleEntry
        fields = ['weekday', 'week_type', 'time_slot', 'group', 'teacher', 'subject', 'room']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ограничиваем выбор преподавателей только учителями
        self.fields['teacher'].queryset = CustomUser.objects.filter(role='teacher')
        # Можно ограничить группы, предметы, кабинеты, если нужно
        # self.fields['group'].queryset = Group.objects.filter(...) 

    def clean(self):
        cleaned_data = super().clean()
        weekday = cleaned_data.get("weekday")
        week_type = cleaned_data.get("week_type")
        time_slot = cleaned_data.get("time_slot") # Используем time_slot
        room = cleaned_data.get("room")
        teacher = cleaned_data.get("teacher")
        group = cleaned_data.get("group")

        # Проверяем, что все необходимые данные заполнены
        if not all([weekday is not None, week_type, time_slot, room, teacher, group]):
            # Если какие-то поля не заполнены, стандартная валидация полей сработает
            return cleaned_data

        # Базовый QuerySet для проверок
        base_qs = ScheduleEntry.objects.filter(
            weekday=weekday,
            week_type=week_type,
            time_slot=time_slot # Используем time_slot
        )

        # Проверка на конфликт по кабинету
        if room:
            overlapping_rooms = base_qs.filter(room=room)
            if self.instance.pk:
                overlapping_rooms = overlapping_rooms.exclude(pk=self.instance.pk)
            if overlapping_rooms.exists():
                raise forms.ValidationError(_("Этот кабинет уже занят в выбранное время и день."))

        # Проверка на конфликт по преподавателю
        if teacher:
            overlapping_teachers = base_qs.filter(teacher=teacher)
            if self.instance.pk:
                overlapping_teachers = overlapping_teachers.exclude(pk=self.instance.pk)
            if overlapping_teachers.exists():
                raise forms.ValidationError(_("Этот преподаватель уже занят в выбранное время и день."))

        # Проверка на конфликт по группе
        if group:
            overlapping_groups = base_qs.filter(group=group)
            if self.instance.pk:
                overlapping_groups = overlapping_groups.exclude(pk=self.instance.pk)
            if overlapping_groups.exists():
                raise forms.ValidationError(_("Эта группа уже занята в выбранное время и день."))

        return cleaned_data


# Форма для выбора группы при создании расписания (если используется отдельно)
class GroupScheduleForm(forms.Form):
    group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        label=_("Выберите группу"),
        required=True
    )


# Форма для импорта данных из Excel
class ImportExcelForm(forms.Form):
    excel_file = forms.FileField(
        label=_('Excel файл'),
        required=True,
        help_text=_('Выберите файл Excel с таблицей студентов и оценок')
    )
    group_name = forms.CharField(
        max_length=100,
        required=True,
        label=_('Название группы'),
        help_text=_('Введите название группы для этих студентов')
    )
    overwrite = forms.BooleanField(
        required=False,
        initial=False,
        label=_('Перезаписать существующие данные'),
        help_text=_('Отметьте для обновления существующих оценок')
    )
    preview_only = forms.BooleanField(
        required=False,
        initial=True,
        label=_('Только предварительный просмотр'),
        help_text=_('Сначала покажите, что будет импортировано')
    )