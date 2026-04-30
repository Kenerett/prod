from django.contrib import admin
from django.shortcuts import render, redirect
from django.urls import path
from django.contrib import messages
from django.core.management import call_command
import os
import tempfile
import pandas as pd
from io import StringIO
import sys
from .views import ImportExcelView
from django import views
from django.utils import timezone

from .models import (
    CustomUser, StudentProfile, Subject, Group, 
    TeacherAssignment, Grade, Attendance, GlobalGradeSettings, Material, TutorProfile, Room, ScheduleEntry, Semester
)
from .forms import CustomUserCreationForm, CustomUserChangeForm


# GradeAdmin with improved import button
@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ['student', 'get_subject', 'get_teacher', 'activity', 'midterm', 'final', 'total']
    list_filter = ['teacher_assignment__subject', 'teacher_assignment__group']
    search_fields = ['student__user__username', 'student__user__first_name', 'student__user__last_name']

    def get_subject(self, obj):
        return obj.teacher_assignment.subject.name
    get_subject.short_description = 'Subject'

    def get_teacher(self, obj):
        return obj.teacher_assignment.teacher.get_full_name()
    get_teacher.short_description = 'Teacher'

    # --- Ограничения доступа ---
    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        # Тьютор НЕ имеет доступа к оценкам через админку
        return False

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return False

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return False

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return False

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return False

    # ... (остальные методы GradeAdmin остаются без изменений)
    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('ImportExcelView/',
                 ImportExcelView.as_view(),
                 name='ImportExcelView'),
        ]
        return my_urls + urls
    
    # Add import button to changelist
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['import_url'] = 'admin:ImportExcelView'
        return super().changelist_view(request, extra_context=extra_context)

    def import_excel_view(self, request):
        """Page for importing student grades from Excel"""
        from django import forms
        
        class StudentGradeImportForm(forms.Form):
            excel_file = forms.FileField(
                label='Excel file with student table',
                required=True,
                help_text='Upload an Excel file with a table where the first column is student names, others are grades'
            )
            group_name = forms.CharField(
                max_length=100,
                required=True,
                label='Group name',
                help_text='Enter the group name for these students'
            )
            overwrite = forms.BooleanField(
                required=False,
                initial=False,
                label='Overwrite existing grades',
                help_text='Check to update existing grades'
            )
            preview_only = forms.BooleanField(
                required=False,
                initial=True,
                label='Preview only',
                help_text='First show what will be imported'
            )
        
        if request.method == 'POST':
            form = StudentGradeImportForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    excel_file = form.cleaned_data['excel_file']
                    group_name = form.cleaned_data['group_name']
                    overwrite = form.cleaned_data['overwrite']
                    preview_only = form.cleaned_data['preview_only']
                    
                    # Save temporary file
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
                        for chunk in excel_file.chunks():
                            tmp_file.write(chunk)
                        tmp_file_path = tmp_file.name

                    try:
                        if preview_only:
                            # Show preview
                            preview_data = self.preview_excel_data(tmp_file_path)
                            context = {
                                'form': form,
                                'preview_data': preview_data,
                                'title': 'Import Preview',
                                'opts': self.model._meta,
                                'has_view_permission': True,
                                'app_label': self.model._meta.app_label,
                            }
                            return render(request, 'admin/import_excel.html', context)
                        else:
                            # Perform real import
                            old_stdout = sys.stdout
                            sys.stdout = captured_output = StringIO()

                            try:
                                args = ['--file', tmp_file_path, '--group', group_name]
                                if overwrite:
                                    args.append('--overwrite')
                                
                                call_command('import_excel_data', *args)
                                
                                output = captured_output.getvalue()
                                messages.success(request, f'Import completed successfully!')
                                messages.info(request, f'Details: {output}')
                                
                            finally:
                                sys.stdout = old_stdout
                                
                            return redirect('admin:school_grade_changelist')
                            
                    finally:
                        if os.path.exists(tmp_file_path):
                            os.remove(tmp_file_path)
                            
                except Exception as e:
                    messages.error(request, f"Import error: {str(e)}")
        else:
            form = StudentGradeImportForm()
        
        context = {
            'form': form,
            'title': 'Import Student Grades from Excel',
            'opts': self.model._meta,
            'has_view_permission': True,
            'app_label': self.model._meta.app_label,
        }
        
        return render(request, 'admin/import_excel.html', context)

    def preview_excel_data(self, file_path):
        """Preview Excel file data"""
        try:
            df = pd.read_excel(file_path)
            
            preview_data = {
                'total_rows': len(df),
                'columns': list(df.columns),
                'sample_students': [],
                'column_analysis': {}
            }
            
            # Analyze columns
            for i, col in enumerate(df.columns):
                col_name = str(col).lower().strip()
                if i == 0:
                    preview_data['column_analysis']['student_names'] = {
                        'column': col,
                        'sample_values': df[col].head(5).tolist()
                    }
                elif any(keyword in col_name for keyword in ['midterm', 'activity', 'final', 'total', 'sg']):
                    preview_data['column_analysis'][col_name] = {
                        'column': col,
                        'sample_values': df[col].head(5).tolist()
                    }
            
            # Show first 10 students
            first_col = df.columns[0]
            student_names = df[first_col].head(10).tolist()
            preview_data['sample_students'] = [str(name) for name in student_names if pd.notna(name)]
            
            return preview_data
            
        except Exception as e:
            return {'error': f'File reading error: {str(e)}'}













# admin.py

from django.contrib import admin
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from .models import CustomUser, Semester, StudentProfile
from .forms import CustomUserCreationForm, CustomUserChangeForm
import logging
import time
import traceback
from django.db import transaction

# Настройка логирования
logger = logging.getLogger(__name__)

class CustomUserAdmin(admin.ModelAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser
    list_display = ['username', 'first_name', 'last_name', 'role', 'email', 'is_active']
    list_filter = ['role', 'is_active']
    search_fields = ['username', 'first_name', 'last_name']
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'middle_name', 'email', 'role')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
        ('Security', {'fields': ('failed_login_attempts', 'lockout_until')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'first_name', 'last_name', 'middle_name', 'role', 'password1', 'password2'),
        }),
    )

    def send_user_credentials_email(self, user, password):
        """Отправка email с данными пользователя"""
        logger.info(f"[EMAIL] Начало отправки email для пользователя {user.username}")
        start_time = time.time()
        
        try:
            logger.info(f"[EMAIL] Подготовка сообщения для {user.email}")
            
            subject = f'Ваши данные для входа в систему'
            message = f'''
Здравствуйте, {user.get_full_name() or user.username}!

Для вас был создан аккаунт в нашей системе.

Данные для входа:
Username: {user.username}
Password: {password}
Email: {user.email}

Пожалуйста, сохраните эти данные в безопасном месте.

С уважением,
Администрация
'''
            
            logger.info(f"[EMAIL] Настройки email:")
            logger.info(f"[EMAIL] - HOST: {settings.EMAIL_HOST}")
            logger.info(f"[EMAIL] - PORT: {settings.EMAIL_PORT}")
            logger.info(f"[EMAIL] - USE_TLS: {settings.EMAIL_USE_TLS}")
            logger.info(f"[EMAIL] - FROM: {settings.DEFAULT_FROM_EMAIL}")
            logger.info(f"[EMAIL] - TO: {user.email}")
            
            logger.info(f"[EMAIL] Отправка email...")
            email_start = time.time()
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            
            email_end = time.time()
            logger.info(f"[EMAIL] Email отправлен успешно за {email_end - email_start:.2f} секунд")
            
            total_time = time.time() - start_time
            logger.info(f"[EMAIL] Общее время отправки email: {total_time:.2f} секунд")
            
            return True
            
        except Exception as e:
            error_time = time.time() - start_time
            logger.error(f"[EMAIL] Ошибка при отправке email после {error_time:.2f} секунд: {str(e)}")
            logger.error(f"[EMAIL] Полная трассировка ошибки:")
            logger.error(traceback.format_exc())
            return False

    def save_model(self, request, obj, form, change):
        """
        Переопределяем сохранение модели для отправки email и создания StudentProfile
        """
        logger.info(f"[SAVE] ========== НАЧАЛО СОХРАНЕНИЯ ПОЛЬЗОВАТЕЛЯ ==========")
        logger.info(f"[SAVE] Пользователь: {obj.username}")
        logger.info(f"[SAVE] Email: {obj.email}")
        logger.info(f"[SAVE] Это новый пользователь: {not change}")
        
        overall_start = time.time()
        
        # Сохраняем пароль перед сохранением пользователя (только при создании)
        password_to_send = None
        if not change and hasattr(form, 'cleaned_data'):
            password_to_send = form.cleaned_data.get('password1')
            logger.info(f"[SAVE] Пароль для отправки получен: {'Да' if password_to_send else 'Нет'}")
        
        # Проверяем, нужно ли создавать пользователя
        is_new_user = not change
        
        try:
            # Сначала сохраняем пользователя
            logger.info(f"[SAVE] Начало сохранения пользователя в БД...")
            db_start = time.time()
            
            with transaction.atomic():
                super().save_model(request, obj, form, change)
                
            db_end = time.time()
            logger.info(f"[SAVE] Пользователь сохранен в БД за {db_end - db_start:.2f} секунд")
            
            # Создание StudentProfile если нужно
            if obj.role == CustomUser.STUDENT and not hasattr(obj, 'student_profile'):
                logger.info(f"[SAVE] Создание StudentProfile...")
                profile_start = time.time()
                
                StudentProfile.objects.create(user=obj)
                
                profile_end = time.time()
                logger.info(f"[SAVE] StudentProfile создан за {profile_end - profile_start:.2f} секунд")
                messages.info(request, f'Автоматически создан StudentProfile для пользователя {obj.username}')
            
            # Обработка изменения роли
            elif change and obj.role != CustomUser.STUDENT and hasattr(obj, 'student_profile'):
                logger.info(f"[SAVE] Удаление StudentProfile...")
                obj.student_profile.delete()
                logger.info(f"[SAVE] StudentProfile удален")
                messages.info(request, f'Удален StudentProfile для пользователя {obj.username} (роль изменена)')
            
            # Отправка email для новых пользователей
            if is_new_user and password_to_send:
                logger.info(f"[SAVE] Начало процесса отправки email...")
                
                # Проверяем настройки email
                if not hasattr(settings, 'EMAIL_HOST_USER') or not settings.EMAIL_HOST_USER:
                    logger.error(f"[SAVE] EMAIL_HOST_USER не настроен!")
                    messages.error(request, f'Пользователь создан, но EMAIL_HOST_USER не настроен')
                    return
                
                if not obj.email:
                    logger.error(f"[SAVE] У пользователя нет email адреса!")
                    messages.error(request, f'Пользователь создан, но у него нет email адреса')
                    return
                
                email_sent = self.send_user_credentials_email(obj, password_to_send)
                
                if email_sent:
                    messages.success(request, f'Пользователь {obj.username} создан. Email с данными отправлен на {obj.email}')
                else:
                    messages.warning(request, f'Пользователь {obj.username} создан, но не удалось отправить email с данными')
                    
        except Exception as e:
            error_time = time.time() - overall_start
            logger.error(f"[SAVE] КРИТИЧЕСКАЯ ОШИБКА после {error_time:.2f} секунд: {str(e)}")
            logger.error(f"[SAVE] Полная трассировка ошибки:")
            logger.error(traceback.format_exc())
            messages.error(request, f'Произошла ошибка при создании/обновлении пользователя: {str(e)}')
            raise
        
        finally:
            total_time = time.time() - overall_start
            logger.info(f"[SAVE] ========== ЗАВЕРШЕНИЕ СОХРАНЕНИЯ ПОЛЬЗОВАТЕЛЯ ==========")
            logger.info(f"[SAVE] Общее время выполнения: {total_time:.2f} секунд")

    # --- Ограничения доступа ---
    def has_module_permission(self, request):
        """Проверяет, должен ли пользователь видеть модуль (CustomUser) в админке."""
        logger.debug(f"[PERM] Проверка has_module_permission для пользователя {request.user.username}")
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            return True
        return False

    def has_view_permission(self, request, obj=None):
        """Проверяет, может ли пользователь просматривать объекты CustomUser."""
        logger.debug(f"[PERM] Проверка has_view_permission для пользователя {request.user.username}")
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            if obj and obj.role != CustomUser.STUDENT:
                return False
            return True
        return False

    def has_add_permission(self, request):
        """Проверяет, может ли пользователь добавлять объекты CustomUser."""
        logger.debug(f"[PERM] Проверка has_add_permission для пользователя {request.user.username}")
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            return True
        return False

    def has_change_permission(self, request, obj=None):
        """Проверяет, может ли пользователь изменять объекты CustomUser."""
        logger.debug(f"[PERM] Проверка has_change_permission для пользователя {request.user.username}")
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            if obj and obj.role == CustomUser.STUDENT:
                return True
            elif obj is None:
                return True
            return False
        return False

    def has_delete_permission(self, request, obj=None):
        """Проверяет, может ли пользователь удалять объекты CustomUser."""
        logger.debug(f"[PERM] Проверка has_delete_permission для пользователя {request.user.username}")
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            return False
        return False

    def get_queryset(self, request):
        logger.debug(f"[QUERY] Получение queryset для пользователя {request.user.username}")
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            return qs.filter(role=CustomUser.STUDENT)
        return qs.none()

# Регистрация модели





    
# --- StudentProfile ---
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'get_group', 'get_all_groups']
    list_filter = ['groups']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']
    filter_horizontal = ('groups',) # Удобный виджет для ManyToMany

    # --- Ограничения доступа ---
    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            return True
        return False

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            # Тьютор может просматривать профили студентов
            # Можно добавить проверку, что студент принадлежит его группе
            if obj:
                try:
                    tutor_profile = request.user.tutor_profile
                    if obj.groups.filter(id__in=tutor_profile.groups.all()).exists():
                        return True
                    else:
                        return False # Не в его группах
                except TutorProfile.DoesNotExist:
                    return False # У тьютора нет профиля
            return True # Разрешить просмотр списка
        return False

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            return True # Тьютор может добавлять профили студентов
        return False

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            # Тьютор может изменять профили студентов
            # Можно добавить проверку, что студент принадлежит его группе
            if obj:
                try:
                    tutor_profile = request.user.tutor_profile
                    if obj.groups.filter(id__in=tutor_profile.groups.all()).exists():
                        return True
                    else:
                        return False # Не в его группах
                except TutorProfile.DoesNotExist:
                    return False # У тьютора нет профиля
            return True # Разрешить доступ к списку для изменения
        return False

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            # Тьютор НЕ может удалять профили студентов
            return False
        return False

    # Опционально: ограничить список отображаемых профилей для тьютора
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            try:
                tutor_profile = request.user.tutor_profile
                # Показываем только студентов из групп тьютора
                return qs.filter(groups__in=tutor_profile.groups.all()).distinct()
            except TutorProfile.DoesNotExist:
                return qs.none() # Если профиля нет, показываем пустой список
        return qs.none()

    # Опционально: ограничить выбор групп при добавлении/изменении
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "groups" and hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            try:
                tutor_profile = request.user.tutor_profile
                kwargs["queryset"] = tutor_profile.groups.all()
            except TutorProfile.DoesNotExist:
                kwargs["queryset"] = Group.objects.none()
        return super().formfield_for_manytomany(db_field, request, **kwargs)




class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'get_group', 'get_all_groups']
    list_filter = ['groups']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']


class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']


class GroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'get_student_count']
    search_fields = ['name']
    filter_horizontal = ['students']

    def get_student_count(self, obj):
        return obj.students.count()
    get_student_count.short_description = 'Number of Students'

    # --- Ограничения доступа ---
    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            return True
        return False

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            # Тьютор может просматривать группы
            # Можно добавить проверку, что это его группа
            if obj:
                try:
                    tutor_profile = request.user.tutor_profile
                    if tutor_profile.groups.filter(id=obj.id).exists():
                        return True
                    else:
                        return False # Не его группа
                except TutorProfile.DoesNotExist:
                    return False # У тьютора нет профиля
            return True # Разрешить просмотр списка
        return False

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            return True # Тьютор может создавать группы
        return False

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            # Тьютор может изменять группы
            # Можно добавить проверку, что это его группа
            if obj:
                try:
                    tutor_profile = request.user.tutor_profile
                    if tutor_profile.groups.filter(id=obj.id).exists():
                        return True
                    else:
                        return False # Не его группа
                except TutorProfile.DoesNotExist:
                    return False # У тьютора нет профиля
            return True # Разрешить доступ к списку для изменения
        return False

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            # Тьютор НЕ может удалять группы
            return False
        return False

    # Опционально: ограничить список отображаемых групп для тьютора
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'role') and request.user.role == CustomUser.TUTOR:
            try:
                tutor_profile = request.user.tutor_profile
                # Показываем только группы тьютора
                return tutor_profile.groups.all()
            except TutorProfile.DoesNotExist:
                return qs.none() # Если профиля нет, показываем пустой список
        return qs.none()




    def get_student_count(self, obj):
        return obj.students.count()
    get_student_count.short_description = 'Number of Students'


class TeacherAssignmentAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'subject', 'group', 'num_sg']
    list_filter = ['subject', 'group']
    search_fields = ['teacher__username', 'teacher__first_name', 'teacher__last_name', 'subject__name']


class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['student', 'get_subject', 'date', 'missed_lessons', 'reason']
    list_filter = ['date', 'teacher_assignment__subject']
    search_fields = ['student__user__username', 'student__user__first_name', 'student__user__last_name']

    def get_subject(self, obj):
        return obj.teacher_assignment.subject.name
    get_subject.short_description = 'Subject'


class MaterialAdmin(admin.ModelAdmin):
    list_display = ['title', 'get_subject', 'get_teacher', 'uploaded_at']
    list_filter = ['teacher_assignment__subject', 'uploaded_at']

    def get_subject(self, obj):
        return obj.teacher_assignment.subject.name
    get_subject.short_description = 'Subject'

    def get_teacher(self, obj):
        return obj.teacher_assignment.teacher.get_full_name()
    get_teacher.short_description = 'Teacher'


class TutorProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'get_groups']
    filter_horizontal = ['groups']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']

    def get_groups(self, obj):
        return ", ".join([group.name for group in obj.groups.all()])
    get_groups.short_description = 'Groups'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            kwargs["queryset"] = CustomUser.objects.filter(role=CustomUser.TUTOR)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # --- Ограничения доступа ---
    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        # Тьютор НЕ имеет доступа к профилям тьюторов через админку
        return False

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return False

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return False

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return False

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return False

class RoomAdmin(admin.ModelAdmin):
    list_display = ['number', 'building', 'capacity']
    search_fields = ['number', 'building']
    list_filter = ['building']


@admin.register(ScheduleEntry)
class ScheduleEntryAdmin(admin.ModelAdmin):
    list_display = [
        'week_type',     
        'weekday',       
        'time_slot',     
        'group',         
        'teacher',       
        'subject',       
        'room',          
        'scheduler'      
    ]
    
    list_filter = [
        'week_type', 
        'weekday', 
        'time_slot',   
        'group', 
        'teacher', 
        'subject', 
        'room', 
        'scheduler'
    ]
    
    search_fields = [
        'group__name',        
        'teacher__first_name', 'teacher__last_name', 
        'subject__name',      
        'room__number',       
    ]


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ['number', 'start_date', 'end_date', 'is_current']
    list_filter = ['number']
    search_fields = ['number']
    ordering = ['number']
    
    def is_current(self, obj):
        today = timezone.now().date()
        return obj.start_date <= today <= obj.end_date
    is_current.boolean = True
    is_current.short_description = 'Current Semester'


@admin.register(GlobalGradeSettings)
class GlobalGradeSettingsAdmin(admin.ModelAdmin):
    """
    Admin for global grade settings.
    Uses custom template to ensure only one record is displayed.
    """
    list_display = ('midterm_limit', 'final_limit')
    
    def has_add_permission(self, request):
        # Allow adding only if no records exist
        return not GlobalGradeSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Disable deletion
        return False

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """
        Redirect to edit page of single record.
        """
        try:
            obj = GlobalGradeSettings.objects.get(pk=1)
            return super().change_view(request, str(obj.pk), form_url, extra_context)
        except GlobalGradeSettings.DoesNotExist:
            return super().changelist_view(request, extra_context)









from django.contrib import admin
from .models import RequestLog

# @admin.register(RequestLog)
# class RequestLogAdmin(admin.ModelAdmin):
#     list_display = ['timestamp', 'ip_address', 'user', 'url', 'method', 'is_authenticated']
#     list_filter = ['is_authenticated', 'method', 'timestamp', 'user']
#     search_fields = ['ip_address', 'url', 'user__username']
#     readonly_fields = ['user', 'ip_address', 'user_agent', 'referer', 'url', 'method', 'timestamp', 'is_authenticated', 'session_key', 'data']
#     date_hierarchy = 'timestamp'

#     def has_add_permission(self, request):
#         return False

#     def has_change_permission(self, request, obj=None):
#         return False

#     def has_delete_permission(self, request, obj=None):
#         return True

# school/admin.py
# school/admin.py
from django.contrib import admin
from django.urls import path
from django.shortcuts import render
from .models import RequestLog

# school/admin.py
from django.contrib import admin
from django.urls import path
from django.shortcuts import render
from .models import RequestLog

@admin.register(RequestLog)
class RequestLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'ip_address', 'user', 'url', 'method', 'is_authenticated']
    list_filter = ['is_authenticated', 'method', 'timestamp', 'user']
    search_fields = ['ip_address', 'url', 'user__username']
    readonly_fields = ['user', 'ip_address', 'user_agent', 'referer', 'url', 'method', 'timestamp', 'is_authenticated', 'session_key', 'data']
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return True

    def get_urls(self):
        # Получаем оригинальные URL
        urls = super().get_urls()
        # Используем admin.site.admin_view
        custom_urls = [
            path('analytics/', admin.site.admin_view(self.analytics_view), name='school_requestlog_analytics'),
        ]
        return custom_urls + urls

    def analytics_view(self, request):
        if not request.user.is_staff:
            return admin.site.login(request)
            
        context = {
            'visits_today': RequestLog.get_visits_today(),
            'visits_week': RequestLog.get_visits_this_week(),
            'visits_month': RequestLog.get_visits_this_month(),
            'current_users': RequestLog.get_current_users(),
            'current_guests': RequestLog.get_current_guests(),
            'total_visits': RequestLog.objects.count(),
        }
        return render(request, 'templates/admin/analytics.html', context)








admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(StudentProfile, StudentProfileAdmin)
admin.site.register(Subject, SubjectAdmin)
admin.site.register(Group, GroupAdmin)
admin.site.register(TeacherAssignment, TeacherAssignmentAdmin)
admin.site.register(Attendance, AttendanceAdmin)
admin.site.register(Material, MaterialAdmin)
admin.site.register(TutorProfile, TutorProfileAdmin)
admin.site.register(Room, RoomAdmin)
admin.site.site_header = 'School Management System'
admin.site.site_title = 'Admin Panel'
admin.site.index_title = 'Welcome to School Management System'