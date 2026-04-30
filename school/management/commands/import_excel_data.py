# management/commands/import_excel_data.py
import logging
import pandas as pd
import re
import time
import traceback
import uuid
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
from django.db.models import Q
from school.models import (
    CustomUser, StudentProfile, Subject, Group,
    TeacherAssignment, Grade, Semester, GlobalGradeSettings
)

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Импорт данных студентов и оценок из Excel файла с горизонтальной разбивкой по семестрам'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, required=True, help='Путь к Excel файлу')
        parser.add_argument('--group', type=str, required=True, help='Название группы')
        parser.add_argument('--overwrite', action='store_true', help='Перезаписать существующие оценки')
        parser.add_argument('--debug', action='store_true', help='Режим отладки')

    def handle(self, *args, **options):
        start_time = time.time()
        file_path = options['file']
        group_name = options['group']
        overwrite = options.get('overwrite', False)
        debug = options.get('debug', False)

        # Загружаем настройки оценок ОДИН РАЗ — не внутри цикла
        self.grade_settings = GlobalGradeSettings.load()

        logger.debug(f"Начало импорта. Файл: {file_path}, Группа: {group_name}, Overwrite: {overwrite}")

        try:
            df = pd.read_excel(file_path, header=None)

            if df.empty:
                raise CommandError("Файл Excel пуст.")

            self.stdout.write(f"Прочитан файл: {file_path}")
            self.stdout.write(f"Строк: {len(df)}, Колонок: {len(df.columns)}")

            group_identifier_row_idx = 0
            subject_header_row_idx = 1
            credits_row_idx = 2
            data_start_row_idx = 3

            estimated_students = max(0, len(df) - data_start_row_idx)
            estimated_subjects = max(0, len(df.columns) - 2)
            estimated_time_minutes = max(2, estimated_students * estimated_subjects * 0.05 / 60)

            self.stdout.write(f"Студентов: ~{estimated_students}, Предметов: ~{estimated_subjects}, Время: ~{estimated_time_minutes:.1f} мин")

            group, created = Group.objects.get_or_create(name=group_name)
            self.stdout.write(f"{'Создана' if created else 'Используется'} группа: {group_name}")

            default_teacher = self._get_or_create_default_teacher()

            column_semester_mapping = self._analyze_semester_structure_from_headers(df, group_identifier_row_idx)
            logger.debug(f"Маппинг колонок и семестров: {column_semester_mapping}")

            used_semester_numbers = set(column_semester_mapping.values())
            semester_objects = self._get_or_create_semesters_for_group(used_semester_numbers, group_name)

            subjects_mapping = self._create_subjects_mapping(
                df, subject_header_row_idx, credits_row_idx,
                column_semester_mapping, semester_objects, default_teacher, group_name
            )
            self.stdout.write(f"Предметов в маппинге: {len(subjects_mapping)}")

            existing_users = self._preload_existing_users()
            existing_profiles = self._preload_existing_profiles(group)

            processed_students = 0
            skipped_rows = 0
            progress_step = max(1, estimated_students // 20)

            with transaction.atomic():
                for row_idx in range(data_start_row_idx, len(df)):
                    if processed_students > 0 and processed_students % progress_step == 0:
                        elapsed = time.time() - start_time
                        remaining = estimated_students - processed_students
                        avg = elapsed / processed_students
                        self.stdout.write(
                            f"Прогресс: {processed_students}/{estimated_students} "
                            f"(~{remaining * avg / 60:.1f} мин осталось)"
                        )

                    row = df.iloc[row_idx]
                    student_name_cell = row.iloc[0] if len(row) > 0 else None

                    if pd.isna(student_name_cell) or not isinstance(student_name_cell, str):
                        skipped_rows += 1
                        continue

                    student_name = str(student_name_cell).strip()
                    if not student_name or student_name.lower() in [
                        'nan', 'name', '', 'фамилия имя отчество', 'credit', 'mails'
                    ]:
                        skipped_rows += 1
                        continue

                    student_email = None
                    email_cell = row.iloc[1] if len(row) > 1 else None
                    if email_cell is not None and not pd.isna(email_cell) and isinstance(email_cell, str):
                        email_str = str(email_cell).strip()
                        if email_str and '@' in email_str and '.' in email_str:
                            student_email = email_str

                    student_profile = self._create_or_get_student_optimized(
                        student_name, group, student_email, existing_users, existing_profiles
                    )

                    if not student_profile:
                        logger.warning(f"Не удалось создать/найти профиль для '{student_name}'")
                        skipped_rows += 1
                        continue

                    self._process_grades_batch(row, subjects_mapping, student_profile, overwrite)
                    processed_students += 1

                    if debug and processed_students <= 3:
                        self.stdout.write(
                            f"[DEBUG] Студент #{processed_students}: {student_name}, "
                            f"email={student_email}, profile_id={student_profile.id}"
                        )

            elapsed_time = time.time() - start_time
            self.stdout.write(self.style.SUCCESS("\n=== ИТОГИ ИМПОРТА ==="))
            self.stdout.write(f"Обработано студентов: {processed_students}")
            self.stdout.write(f"Пропущено строк: {skipped_rows}")
            self.stdout.write(f"Предметов: {len(subjects_mapping)}")
            self.stdout.write(f"Время: {elapsed_time:.2f} сек ({elapsed_time / 60:.1f} мин)")
            self.stdout.write(self.style.SUCCESS("Импорт завершен успешно!"))

        except FileNotFoundError:
            error_msg = f'Файл не найден: {file_path}'
            self.stdout.write(self.style.ERROR(error_msg))
            raise CommandError(error_msg)
        except Exception as e:
            tb = traceback.format_exc()
            error_msg = f'Ошибка при импорте: {str(e)}'
            self.stdout.write(self.style.ERROR(error_msg))
            self.stdout.write(self.style.ERROR(tb))
            raise CommandError(f'{error_msg}\n{tb}')

    # -------------------------------------------------------------------------

    def _analyze_semester_structure_from_headers(self, df, group_identifier_row_idx):
        column_semester_mapping = {}

        if len(df) <= group_identifier_row_idx:
            logger.warning("Строка с заголовками отсутствует")
            return column_semester_mapping

        header_row = df.iloc[group_identifier_row_idx]
        current_semester_num = 1
        SUMMARY_KEYWORDS = {'gpa', 'total', 'итого', 'средний', 'credits', 'credit'}

        for col_idx in range(2, len(header_row)):
            cell = header_row.iloc[col_idx] if col_idx < len(header_row) else None

            if pd.notna(cell) and isinstance(cell, str):
                cell_text = cell.strip().lower()

                if any(kw in cell_text for kw in SUMMARY_KEYWORDS):
                    continue

                if any(kw in cell_text for kw in ('semester', 'семестр')):
                    found_num = self._extract_semester_number(cell_text)
                    if found_num and 1 <= found_num <= 20:
                        current_semester_num = found_num

            column_semester_mapping[col_idx] = current_semester_num

        logger.debug(f"Маппинг семестров: {column_semester_mapping}")
        return column_semester_mapping

    def _extract_semester_number(self, text):
        text_lower = text.lower()
        roman_patterns = [
            ('viii', 8), ('vii', 7), ('vi', 6), ('v', 5),
            ('iv', 4), ('iii', 3), ('ii', 2), ('i', 1)
        ]
        for roman, num in roman_patterns:
            if roman in text_lower:
                return num

        match = re.search(r'\b([1-9]|1[0-9]|20)\b', text)
        if match:
            return int(match.group(1))

        return None

    def _get_or_create_semesters_for_group(self, semester_numbers, group_name):
        semester_objects = {}
        for sem_num in semester_numbers:
            if not isinstance(sem_num, int) or not (1 <= sem_num <= 20):
                logger.warning(f"Недопустимый номер семестра: {sem_num}")
                continue

            unique_name = f"Semester {sem_num} ({group_name})"
            semester_obj, created = Semester.objects.get_or_create(
                name=unique_name,
                defaults={
                    'number': sem_num,
                    'start_date': '2023-09-01',
                    'end_date': '2024-01-31',
                }
            )
            logger.debug(f"{'Создан' if created else 'Найден'} семестр '{unique_name}'")
            semester_objects[sem_num] = semester_obj

        return semester_objects

    def _preload_existing_users(self):
        users = CustomUser.objects.filter(role=CustomUser.STUDENT)
        result = {(u.first_name.lower(), u.last_name.lower()): u for u in users}
        logger.debug(f"Предзагружено пользователей-студентов: {len(result)}")
        return result

    def _preload_existing_profiles(self, group):
        profiles = StudentProfile.objects.filter(groups=group).select_related('user')
        result = {p.user_id: p for p in profiles}
        logger.debug(f"Предзагружено профилей для группы {group.name}: {len(result)}")
        return result

    def _process_grades_batch(self, row, subjects_mapping, student_profile, overwrite):
        SKIP_VALUES = {'np', 'n/a', 'absent', 'отсутствовал', '-', 'gpa', 'total', 'credit', 'credits', 'mails'}

        existing_grades = {
            (g.teacher_assignment_id, g.semester_id): g
            for g in Grade.objects.filter(student=student_profile)
        }

        grades_to_create = []
        grades_to_update = []

        for col_idx, subject_info in subjects_mapping.items():
            if col_idx >= len(row):
                continue

            raw = row.iloc[col_idx]
            if pd.isna(raw) or str(raw).strip() == '':
                continue
            if str(raw).strip().lower() in SKIP_VALUES:
                continue

            try:
                grade_value = float(str(raw).replace(',', '.')) if isinstance(raw, str) else float(raw)
            except (ValueError, TypeError):
                logger.debug(f"Не удалось конвертировать значение оценки: '{raw}'")
                continue

            grade_key = (subject_info['assignment'].id, subject_info['semester'].id)
            existing = existing_grades.get(grade_key)

            if existing:
                if overwrite:
                    scores = existing.additional_scores or {}
                    scores[subject_info['subject'].name] = grade_value
                    existing.additional_scores = scores
                    existing.total = grade_value
                    grades_to_update.append(existing)
            else:
                grades_to_create.append(Grade(
                    student=student_profile,
                    teacher_assignment=subject_info['assignment'],
                    semester=subject_info['semester'],
                    additional_scores={subject_info['subject'].name: grade_value},
                    total=grade_value,
                ))

        if grades_to_create:
            # bulk_create обходит Grade.save() — full_clean() не вызывается,
            # GlobalGradeSettings.load() тоже, что и является целью оптимизации
            Grade.objects.bulk_create(grades_to_create, batch_size=100)
            logger.debug(f"Создано оценок: {len(grades_to_create)}")

        if grades_to_update:
            Grade.objects.bulk_update(grades_to_update, ['additional_scores', 'total'], batch_size=100)
            logger.debug(f"Обновлено оценок: {len(grades_to_update)}")

    def _create_or_get_student_optimized(self, full_name, group, email, existing_users, existing_profiles):
        if not full_name or not isinstance(full_name, str):
            return None

        name_parts = full_name.split()
        if len(name_parts) >= 2:
            last_name = name_parts[0]
            first_name = name_parts[1]
            middle_name = ' '.join(name_parts[2:])
        elif len(name_parts) == 1:
            last_name = name_parts[0]
            first_name = 'Student'
            middle_name = ''
        else:
            return None

        user_key = (first_name.lower(), last_name.lower())
        student_user = existing_users.get(user_key)

        if student_user:
            if email and not student_user.email:
                student_user.email = email
                student_user.save(update_fields=['email'])
        else:
            username = self._generate_username_optimized(first_name, last_name, existing_users)
            student_user = CustomUser(
                username=username,
                first_name=first_name,
                last_name=last_name,
                middle_name=middle_name,
                email=email or '',
                role=CustomUser.STUDENT,
            )
            student_user.set_password('defaultpassword123')
            student_user.save()
            existing_users[user_key] = student_user
            logger.debug(f"Создан пользователь: {student_user.username}")

        student_profile = self._get_or_create_student_profile(student_user, existing_profiles, group)

        if not student_profile and not existing_users.get(user_key):
            # Откатываем создание пользователя если профиль не удалось создать
            student_user.delete()
            return None

        return student_profile

    def _get_or_create_student_profile(self, student_user, existing_profiles, group):
        profile = existing_profiles.get(student_user.id)
        if profile:
            if not profile.groups.filter(pk=group.pk).exists():
                profile.groups.add(group)
            return profile

        try:
            profile = StudentProfile.objects.get(user=student_user)
        except StudentProfile.DoesNotExist:
            try:
                profile = StudentProfile.objects.create(user=student_user)
            except IntegrityError:
                try:
                    profile = StudentProfile.objects.get(user=student_user)
                except StudentProfile.DoesNotExist:
                    logger.error(f"Не удалось создать профиль для {student_user.username}")
                    return None
            except Exception as e:
                logger.error(f"Ошибка создания профиля для {student_user.username}: {e}")
                return None

        existing_profiles[student_user.id] = profile
        if not profile.groups.filter(pk=group.pk).exists():
            profile.groups.add(group)
        return profile

    def _generate_username_optimized(self, first_name, last_name, existing_users):
        base = re.sub(r'[^a-z0-9.]', '', f"{first_name.lower()}.{last_name.lower()}")
        if not base:
            base = f"user.{len(existing_users) + 1}"

        username = base
        counter = 1
        while CustomUser.objects.filter(username=username).exists():
            username = f"{base}{counter}"
            counter += 1
            if counter > 1000:
                username = f"{base}_{uuid.uuid4().hex[:8]}"
                break

        return username

    def _create_subjects_mapping(self, df, subject_row_idx, credits_row_idx,
                                  column_semester_mapping, semester_objects,
                                  default_teacher, group_name):
        subjects_mapping = {}
        if len(df) <= subject_row_idx or len(df) <= credits_row_idx:
            return subjects_mapping

        subject_row = df.iloc[subject_row_idx]
        credits_row = df.iloc[credits_row_idx]
        SKIP_NAMES = {'gpa', 'total', 'credit', 'credits', 'mails', ''}
        group_suffix = f" ({group_name})"

        for col_idx in range(2, len(subject_row)):
            cell = subject_row.iloc[col_idx] if col_idx < len(subject_row) else None
            if pd.isna(cell):
                continue

            subject_name = str(cell).strip()
            if not subject_name or subject_name.lower() in SKIP_NAMES:
                continue

            semester_num = column_semester_mapping.get(col_idx)
            if semester_num is None:
                logger.warning(f"Семестр не найден для колонки {col_idx} ({subject_name}), пропуск")
                continue

            semester_obj = semester_objects.get(semester_num)
            if not semester_obj:
                logger.warning(f"Объект семестра {semester_num} не найден, пропуск")
                continue

            credits_value = 0
            if col_idx < len(credits_row):
                credits_cell = credits_row.iloc[col_idx]
                if credits_cell is not None and not pd.isna(credits_cell):
                    try:
                        credits_value = int(float(credits_cell))
                    except (ValueError, TypeError):
                        pass

            unique_subject_name = f"{subject_name}{group_suffix}"

            subject_obj, created = Subject.objects.get_or_create(
                name=unique_subject_name,
                defaults={
                    'description': f'Предмет: {subject_name} (Группа: {group_name}, Семестр: {semester_num})',
                    'credits': credits_value,
                }
            )
            if not created and subject_obj.credits != credits_value and credits_value > 0:
                subject_obj.credits = credits_value
                subject_obj.save(update_fields=['credits'])

            assignment = self._get_or_create_assignment(default_teacher, group_name, subject_obj, semester_obj)
            subjects_mapping[col_idx] = {
                'subject': subject_obj,
                'teacher': default_teacher,
                'assignment': assignment,
                'semester': semester_obj,
            }

        logger.debug(f"Создано записей в маппинге: {len(subjects_mapping)}")
        return subjects_mapping

    def _get_or_create_assignment(self, teacher, group_name, subject, semester):
        group, _ = Group.objects.get_or_create(name=group_name)

        assignment = TeacherAssignment.objects.filter(
            teacher=teacher, group=group, subject=subject, semester=semester
        ).first()

        if not assignment:
            try:
                assignment = TeacherAssignment.objects.create(
                    teacher=teacher, group=group, subject=subject,
                    semester=semester, num_sg=0
                )
            except Exception as e:
                logger.warning(f"Ошибка создания назначения, повторный поиск: {e}")
                assignment = TeacherAssignment.objects.filter(
                    teacher=teacher, group=group, subject=subject
                ).first()
                if not assignment:
                    assignment = TeacherAssignment.objects.create(
                        teacher=teacher, group=group, subject=subject, num_sg=0
                    )

        return assignment

    def _get_or_create_default_teacher(self):
        user, created = CustomUser.objects.get_or_create(
            username='default_teacher',
            defaults={
                'first_name': 'Default',
                'last_name': 'Teacher',
                'role': CustomUser.TEACHER,
            }
        )
        if created or not user.has_usable_password():
            user.set_password('defaultpassword123')
            user.save(update_fields=['password'])

        logger.debug(f"{'Создан' if created else 'Найден'} преподаватель по умолчанию")
        return user