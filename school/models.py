# school/models.py
import datetime
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.conf import settings
from datetime import timedelta
import json


class CustomUser(AbstractUser):
    TEACHER = 'teacher'
    STUDENT = 'student'
    TUTOR = 'tutor'
    SCHEDULER = 'scheduler'

    ROLE_CHOICES = (
        (TEACHER, 'Teacher'),
        (STUDENT, 'Student'),
        (TUTOR, 'Tutor'),
        (SCHEDULER, 'Scheduler'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, verbose_name='Role')
    first_name = models.CharField(max_length=50, verbose_name='First Name')
    last_name = models.CharField(max_length=50, verbose_name='Last Name')
    middle_name = models.CharField(max_length=50, blank=True, null=True, verbose_name='Middle Name')
    email = models.EmailField()
    failed_login_attempts = models.PositiveIntegerField(default=0)
    lockout_until = models.DateTimeField(null=True, blank=True)

    def is_locked(self):
        return self.lockout_until and self.lockout_until > timezone.now()

    def __str__(self):
        parts = [self.last_name, self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        return ' '.join(parts)


class Semester(models.Model):
    number = models.IntegerField()
    name = models.CharField(max_length=200, unique=True, null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()

    def __str__(self):
        return self.name or f"Semester {self.number}"

    class Meta:
        pass


class TutorProfile(models.Model):
    """
    Tutor profile, linked to user.
    """
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'tutor'},
        related_name='tutor_profile'
    )
    groups = models.ManyToManyField(
        'Group',
        blank=True,
        related_name='tutors',
        verbose_name='Groups'
    )

    class Meta:
        verbose_name = 'Tutor Profile'
        verbose_name_plural = 'Tutor Profiles'

    def __str__(self):
        return f"Tutor: {self.user.get_full_name()}"

    def get_full_name(self):
        return self.user.get_full_name()


class StudentProfile(models.Model):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name='student_profile'
    )

    class Meta:
        verbose_name = 'Student Profile'
        verbose_name_plural = 'Student Profiles'

    def get_group(self):
        """Get the first group this student belongs to"""
        first_group = self.groups.first()
        return first_group.name if first_group else '-'

    def get_all_groups(self):
        """Get all groups this student belongs to"""
        return ', '.join([group.name for group in self.groups.all()])

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.get_group()})"

    def get_current_semester(self):
        from school.services.semester import get_current_semester
        return get_current_semester()

    def get_grades_by_semester(self, semester=None):
        if semester is None:
            from school.services.semester import get_current_semester
            semester = get_current_semester()
        return Grade.objects.filter(
            student=self, semester=semester
        ).select_related('teacher_assignment__subject')

    def get_gpa_for_semester(self, semester=None):
        """
        Calculates GPA using weighted formula:
        1. For each subject multiply grade by credits.
        2. Sum all weighted values.
        3. Divide by total credits.
        """
        grades = self.get_grades_by_semester(semester)
        if not grades.exists():
            return None

        total_weighted_score = 0
        total_credits = 0

        for grade in grades:
            if grade.total is not None:
                credits = grade.teacher_assignment.subject.credits or 0
                if credits > 0:
                    total_weighted_score += grade.total * credits
                    total_credits += credits

        if total_credits == 0:
            return None

        return round(total_weighted_score / total_credits, 2)


class Specialty(models.Model):
    """Academic specialty / program (e.g. Mechatronics)."""
    code = models.CharField(max_length=50, unique=True, verbose_name='Specialty Code')
    name = models.CharField(max_length=200, verbose_name='Specialty Name')

    class Meta:
        verbose_name = 'Specialty'
        verbose_name_plural = 'Specialties'
        ordering = ['name']

    def __str__(self):
        return f"{self.code} — {self.name}"


class Subject(models.Model):
    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=20, unique=True, blank=True, null=True, verbose_name='Subject Code')
    description = models.TextField(blank=True, null=True)
    credits = models.IntegerField(default=0)

    def __str__(self):
        return f"[{self.code}] {self.name}" if self.code else self.name


class CurriculumEntry(models.Model):
    """One subject row in a specialty's curriculum."""
    specialty = models.ForeignKey(
        Specialty,
        on_delete=models.CASCADE,
        related_name='curriculum_entries',
        verbose_name='Specialty',
    )
    semester_number = models.PositiveIntegerField(verbose_name='Semester Number')
    subject_code = models.CharField(max_length=20, verbose_name='Subject Code')
    subject_name = models.CharField(max_length=255, verbose_name='Subject Name')
    ects = models.PositiveIntegerField(default=0, verbose_name='ECTS Credits')
    hours_per_week = models.PositiveIntegerField(default=0, verbose_name='Hours/Week')
    prerequisite_codes = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Prerequisite Codes',
        help_text='List of subject codes that must be passed before this one.',
    )
    subject = models.ForeignKey(
        'Subject',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='curriculum_entries',
        verbose_name='Subject (linked)',
    )

    class Meta:
        unique_together = ('specialty', 'subject_code')
        ordering = ['specialty', 'semester_number', 'subject_code']
        verbose_name = 'Curriculum Entry'
        verbose_name_plural = 'Curriculum Entries'

    def __str__(self):
        return f"{self.specialty.name} | Sem {self.semester_number} | {self.subject_code}: {self.subject_name}"

    def get_prerequisite_entries(self):
        return CurriculumEntry.objects.filter(
            specialty=self.specialty,
            subject_code__in=self.prerequisite_codes,
        )


class Group(models.Model):
    name = models.CharField(max_length=50, unique=True)
    specialty = models.ForeignKey(
        Specialty,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='groups',
        verbose_name='Specialty',
    )

    students = models.ManyToManyField(
        StudentProfile,
        blank=True,
        related_name='groups'
    )

    def __str__(self):
        return self.name


class TeacherAssignment(models.Model):
    teacher = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'teacher'},
        related_name='assignments'
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='teacher_assignments'
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='teacher_assignments'
    )
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)

    num_sg = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Number of Quizzes (SG)',
        help_text='Fixed number of quizzes for this group/subject per semester. Set by teacher.'
    )

    class Meta:
        unique_together = ('teacher', 'group', 'subject', 'semester')
        verbose_name = 'Teacher Assignment'
        verbose_name_plural = 'Teacher Assignments'

    def __str__(self):
        return f"{self.teacher.get_full_name()} teaches {self.subject} to {self.group}"

    def get_sg_field_names(self):
        """Generates list of SG field names: ['SG1', 'SG2', ..., 'SG<num_sg>']"""
        count = self.num_sg if self.num_sg is not None else 0
        return [f"SG{i}" for i in range(1, count + 1)] if count > 0 else []


class Grade(models.Model):
    student = models.ForeignKey(
        'StudentProfile',
        on_delete=models.CASCADE,
        verbose_name='Student'
    )
    teacher_assignment = models.ForeignKey(
        'TeacherAssignment',
        on_delete=models.CASCADE,
        verbose_name='Teacher-Subject-Group'
    )

    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)

    activity = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Activity'
    )
    midterm = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Midterm'
    )
    final = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Final'
    )
    total = models.FloatField(
        null=True,
        blank=True,
        verbose_name='Total Score'
    )
    additional_scores = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        verbose_name='Additional Scores'
    )

    class Meta:
        unique_together = ('student', 'teacher_assignment')
        verbose_name = 'Grade'
        verbose_name_plural = 'Grades'

    def clean(self):
        super().clean()
        grade_settings = GlobalGradeSettings.load()

        for field_name in ['activity', 'midterm', 'final']:
            value = getattr(self, field_name)
            if value is None:
                continue
            if not isinstance(value, int):
                raise ValidationError({
                    field_name: f"{field_name.capitalize()} must be an integer."
                })
            max_allowed = 50
            if field_name == 'midterm' and grade_settings.midterm_limit is not None:
                max_allowed = grade_settings.midterm_limit
            elif field_name == 'final' and grade_settings.final_limit is not None:
                max_allowed = grade_settings.final_limit

            if not (0 <= value <= max_allowed):
                if field_name == 'midterm':
                    raise ValidationError({
                        field_name: f"{field_name.capitalize()} must be between 0 and {max_allowed} (limit set by admin)."
                    })
                elif field_name == 'final':
                    raise ValidationError({
                        field_name: f"{field_name.capitalize()} must be between 0 and {max_allowed} (limit set by admin)."
                    })
                else:
                    raise ValidationError({
                        field_name: f"{field_name.capitalize()} must be between 0 and {max_allowed}."
                    })

        if self.additional_scores:
            sg_total = 0
            for key, value in self.additional_scores.items():
                if not key.startswith('SG'):
                    continue
                if not isinstance(value, (int, float)):
                    raise ValidationError({
                        'additional_scores': f"Value '{key}' must be a number."
                    })
                if value < 0:
                    raise ValidationError({
                        'additional_scores': f"Value '{key}' cannot be negative."
                    })
                sg_total += value
            if sg_total > 20:
                raise ValidationError({
                    'additional_scores': f"Total SG score cannot exceed 20. Current: {sg_total}"
                })

    def calculate_sg_total(self):
        """Calculates total score for all SG."""
        if self.additional_scores:
            return sum(v for k, v in self.additional_scores.items() if k.startswith('SG') and isinstance(v, (int, float)))
        return 0

    def calculate_total(self):
        """Calculates total score based on all grades."""
        total = sum(
            getattr(self, field) for field in ['activity', 'midterm', 'final']
            if getattr(self, field) is not None
        )
        total += self.calculate_sg_total()
        return total

    def save(self, *args, **kwargs):
        self.total = self.calculate_total()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} — {self.teacher_assignment.subject}"

    def get_sg_scores(self):
        """Returns dictionary with only SG grades."""
        if self.additional_scores:
            return {k: v for k, v in self.additional_scores.items() if k.startswith('SG')}
        return {}


class Attendance(models.Model):
    student = models.ForeignKey(
        'StudentProfile',
        on_delete=models.CASCADE,
        verbose_name='Student'
    )
    teacher_assignment = models.ForeignKey(
        'TeacherAssignment',
        on_delete=models.CASCADE,
        verbose_name='Teacher-Subject-Group'
    )
    date = models.DateField(verbose_name='Date')
    missed_lessons = models.PositiveIntegerField(
        default=0,
        verbose_name='Missed Lessons',
        help_text='Number of missed lessons'
    )
    reason = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Reason'
    )

    class Meta:
        unique_together = ('student', 'teacher_assignment', 'date')
        verbose_name = 'Attendance'
        verbose_name_plural = 'Attendance'

    def __str__(self):
        return f"{self.student} — {self.teacher_assignment.subject}, {self.date}: {self.missed_lessons} lessons"


class Material(models.Model):
    teacher_assignment = models.ForeignKey(TeacherAssignment, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='materials/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Room(models.Model):
    """Room/auditorium model."""
    number = models.CharField(max_length=20, unique=True, verbose_name='Room Number')
    building = models.CharField(max_length=100, blank=True, verbose_name='Building')
    capacity = models.PositiveIntegerField(blank=True, null=True, verbose_name='Capacity')

    class Meta:
        verbose_name = 'Room'
        verbose_name_plural = 'Rooms'
        ordering = ['number']

    def __str__(self):
        building_part = f" ({self.building})" if self.building else ""
        return f"Room {self.number}{building_part}"


class ScheduleEntry(models.Model):
    """Schedule entry by week."""

    TOP_WEEK = 'top'
    BOTTOM_WEEK = 'bottom'
    WEEK_CHOICES = [
        (TOP_WEEK, 'Top Week'),
        (BOTTOM_WEEK, 'Bottom Week'),
    ]

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6
    WEEKDAY_CHOICES = [
        (MONDAY, 'Monday'),
        (TUESDAY, 'Tuesday'),
        (WEDNESDAY, 'Wednesday'),
        (THURSDAY, 'Thursday'),
        (FRIDAY, 'Friday'),
        (SATURDAY, 'Saturday'),
        (SUNDAY, 'Sunday'),
    ]

    TIME_SLOT_CHOICES = [
        (1, '8:30-9:50'),
        (2, '10:05-11:25'),
        (3, '11:40-13:00'),
        (4, '13:30-14:50'),
        (5, '15:05-16:25'),
        (6, '16:40-18:00'),
    ]

    scheduler = models.ForeignKey(
        'CustomUser',
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'scheduler'},
        related_name='schedule_entries',
        verbose_name='Scheduler'
    )
    weekday = models.IntegerField(choices=WEEKDAY_CHOICES, verbose_name='Day of Week')
    week_type = models.CharField(max_length=10, choices=WEEK_CHOICES, verbose_name='Week Type')
    time_slot = models.IntegerField(choices=TIME_SLOT_CHOICES, default=1, verbose_name='Time Slot')

    group = models.ForeignKey(
        'Group',
        on_delete=models.CASCADE,
        related_name='schedule_entries',
        verbose_name='Group'
    )
    teacher = models.ForeignKey(
        'CustomUser',
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'teacher'},
        related_name='teaching_schedule_entries',
        verbose_name='Teacher'
    )
    subject = models.ForeignKey(
        'Subject',
        on_delete=models.CASCADE,
        related_name='schedule_entries',
        verbose_name='Subject'
    )
    room = models.ForeignKey(
        'Room',
        on_delete=models.CASCADE,
        related_name='schedule_entries',
        verbose_name='Room'
    )

    class Meta:
        verbose_name = 'Schedule Entry'
        verbose_name_plural = 'Schedule Entries'
        ordering = ['week_type', 'weekday', 'time_slot']
        constraints = [
            models.UniqueConstraint(
                fields=['scheduler', 'weekday', 'week_type', 'time_slot', 'teacher'],
                name='unique_teacher_time_slot_per_scheduler'
            ),
            models.UniqueConstraint(
                fields=['scheduler', 'weekday', 'week_type', 'time_slot', 'room'],
                name='unique_room_time_slot_per_scheduler'
            ),
        ]

    def __str__(self):
        week_str = "Top" if self.week_type == self.TOP_WEEK else "Bottom"
        day_str = self.get_weekday_display()
        time_str = self.get_time_slot_display()
        return f"{week_str} week, {day_str} {time_str}: {self.group} - {self.subject}"

    def clean(self):
        pass

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def start_end_time(self):
        """Returns tuple (start_time, end_time) for display."""
        time_map = {
            1: ("08:30", "09:50"),
            2: ("10:05", "11:25"),
            3: ("11:40", "13:00"),
            4: ("13:30", "14:50"),
            5: ("15:05", "16:25"),
            6: ("16:40", "18:00"),
        }
        return time_map.get(self.time_slot, ("", ""))

    @property
    def start_time(self):
        """Returns time object for start of class."""
        from datetime import time
        time_map = {
            1: time(8, 30),
            2: time(10, 5),
            3: time(11, 40),
            4: time(13, 30),
            5: time(15, 5),
            6: time(16, 40),
        }
        return time_map.get(self.time_slot, time(0, 0))

    @property
    def end_time(self):
        """Returns time object for end of class."""
        from datetime import time
        time_map = {
            1: time(9, 50),
            2: time(11, 25),
            3: time(13, 0),
            4: time(14, 50),
            5: time(16, 25),
            6: time(18, 0),
        }
        return time_map.get(self.time_slot, time(0, 0))


class GlobalGradeSettings(models.Model):
    """
    Model for storing global grade settings managed by admin.
    """
    midterm_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Midterm Limit',
        help_text='Maximum allowed value for midterm. Leave blank to allow any value up to 50.'
    )
    final_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Final Limit',
        help_text='Maximum allowed value for final. Leave blank to allow any value up to 50.'
    )

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Loads (or creates) the single settings instance."""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Global Grade Settings"

    class Meta:
        verbose_name = "Global Grade Settings"
        verbose_name_plural = "Global Grade Settings"


class RequestLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
    )
    ip_address = models.GenericIPAddressField(db_index=True)
    user_agent = models.TextField(blank=True, null=True)
    referer = models.TextField(blank=True, null=True)
    url = models.TextField()
    method = models.CharField(max_length=10)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    is_authenticated = models.BooleanField(default=False)
    session_key = models.CharField(max_length=100, blank=True, null=True)
    data = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"{self.ip_address} → {self.url} [{self.timestamp}]"

    @classmethod
    def get_analytics_summary(cls, period='today'):
        now = timezone.now()
        if period == 'today':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'week':
            today = now.date()
            start = now - timedelta(days=today.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'month':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start = now

        qs = cls.objects.filter(timestamp__gte=start)
        five_min_ago = now - timedelta(minutes=5)
        online_qs = cls.objects.filter(timestamp__gte=five_min_ago)

        return {
            'unique_visitors': qs.values('ip_address', 'user').distinct().count(),
            'authenticated_users': online_qs.filter(is_authenticated=True).values('user').distinct().count(),
            'guests': online_qs.filter(is_authenticated=False).values('ip_address').distinct().count(),
            'role_stats': qs.filter(is_authenticated=True, user__isnull=False)
                           .values('user__role')
                           .annotate(count=models.Count('user', distinct=True)),
        }

    @classmethod
    def get_visits_today(cls):
        """Number of unique visitors today"""
        today = timezone.now().date()
        return cls.objects.filter(
            timestamp__date=today
        ).values('ip_address', 'user').distinct().count()

    @classmethod
    def get_visits_this_week(cls):
        """Number of unique visitors this week"""
        today = timezone.now().date()
        start_of_week = today - timedelta(days=today.weekday())
        return cls.objects.filter(
            timestamp__date__gte=start_of_week
        ).values('ip_address', 'user').distinct().count()

    @classmethod
    def get_visits_this_month(cls):
        """Number of unique visitors this month"""
        now = timezone.now()
        start_of_month = now.replace(day=1)
        return cls.objects.filter(
            timestamp__gte=start_of_month
        ).values('ip_address', 'user').distinct().count()

    @classmethod
    def get_current_users(cls):
        """Number of authenticated users online (last 5 minutes)"""
        five_minutes_ago = timezone.now() - timedelta(minutes=5)
        return cls.objects.filter(
            timestamp__gte=five_minutes_ago,
            is_authenticated=True
        ).values('user').distinct().count()

    @classmethod
    def get_current_guests(cls):
        """Number of guest users online (last 5 minutes)"""
        five_minutes_ago = timezone.now() - timedelta(minutes=5)
        return cls.objects.filter(
            timestamp__gte=five_minutes_ago,
            is_authenticated=False
        ).values('ip_address').distinct().count()

    @classmethod
    def get_role_visits_today(cls):
        """Number of unique users by role today"""
        today = timezone.now().date()
        return cls.objects.filter(
            timestamp__date=today,
            is_authenticated=True,
            user__isnull=False
        ).values('user__role').annotate(
            count=models.Count('user', distinct=True)
        )

    @classmethod
    def get_role_visits_this_week(cls):
        """Number of unique users by role this week"""
        today = timezone.now().date()
        start_of_week = today - timedelta(days=today.weekday())
        return cls.objects.filter(
            timestamp__date__gte=start_of_week,
            is_authenticated=True,
            user__isnull=False
        ).values('user__role').annotate(
            count=models.Count('user', distinct=True)
        )

    @classmethod
    def get_role_visits_this_month(cls):
        """Number of unique users by role this month"""
        now = timezone.now()
        start_of_month = now.replace(day=1)
        return cls.objects.filter(
            timestamp__gte=start_of_month,
            is_authenticated=True,
            user__isnull=False
        ).values('user__role').annotate(
            count=models.Count('user', distinct=True)
        )

    @classmethod
    def get_detailed_role_stats(cls, period='today'):
        """Get detailed statistics by role for the given period"""
        if period == 'today':
            today = timezone.now().date()
            logs = cls.objects.filter(
                timestamp__date=today,
                is_authenticated=True,
                user__isnull=False
            )
        elif period == 'week':
            today = timezone.now().date()
            start_of_week = today - timedelta(days=today.weekday())
            logs = cls.objects.filter(
                timestamp__date__gte=start_of_week,
                is_authenticated=True,
                user__isnull=False
            )
        elif period == 'month':
            now = timezone.now()
            start_of_month = now.replace(day=1)
            logs = cls.objects.filter(
                timestamp__gte=start_of_month,
                is_authenticated=True,
                user__isnull=False
            )
        else:
            logs = cls.objects.none()

        role_stats = {}
        for role_key, role_name in CustomUser.ROLE_CHOICES:
            count = logs.filter(user__role=role_key).values('user').distinct().count()
            role_stats[role_name] = count

        return role_stats

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Request Log"
        verbose_name_plural = "LOGS"


class StudentExtendedInfo(models.Model):
    """Additional student data imported from LMS (Sheet 1 of import file)."""
    student = models.OneToOneField(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='extended_info',
        verbose_name='Student',
    )
    fin_code = models.CharField(max_length=20, blank=True, null=True, verbose_name='FIN')
    faculty = models.CharField(max_length=200, blank=True, null=True, verbose_name='Faculty')
    specialty_code = models.CharField(max_length=50, blank=True, null=True, verbose_name='Specialty Code')
    specialty_name = models.CharField(max_length=200, blank=True, null=True, verbose_name='Specialty')
    education_form = models.CharField(max_length=50, blank=True, null=True, verbose_name='Education Form')
    education_level = models.CharField(max_length=50, blank=True, null=True, verbose_name='Education Level')
    date_of_birth = models.DateField(null=True, blank=True, verbose_name='Date of Birth')
    gender = models.CharField(max_length=1, blank=True, null=True, verbose_name='Gender')
    citizenship = models.CharField(max_length=50, blank=True, null=True, verbose_name='Citizenship')
    birth_city = models.CharField(max_length=200, blank=True, null=True, verbose_name='Birth City/District')
    address = models.TextField(blank=True, null=True, verbose_name='Address')
    phone = models.CharField(max_length=50, blank=True, null=True, verbose_name='Phone')
    status = models.CharField(max_length=100, blank=True, null=True, verbose_name='Study Status')
    admission_year = models.IntegerField(null=True, blank=True, verbose_name='Admission Year')
    admission_score = models.FloatField(null=True, blank=True, verbose_name='Admission Score')
    study_year = models.IntegerField(null=True, blank=True, verbose_name='Study Year (Course)')
    gets_scholarship = models.BooleanField(null=True, blank=True, verbose_name='Gets Scholarship')
    id_card_series = models.CharField(max_length=10, blank=True, null=True, verbose_name='ID Card Series')
    id_card_number = models.CharField(max_length=20, blank=True, null=True, verbose_name='ID Card Number')
    student_card_number = models.CharField(max_length=20, blank=True, null=True, verbose_name='Student Card Number')

    class Meta:
        verbose_name = 'Student Extended Info'
        verbose_name_plural = 'Student Extended Info'

    def __str__(self):
        return f"Extended info: {self.student}"


class LMSGrade(models.Model):
    """
    Cumulative grade per subject imported from LMS grade sheets.
    Stores the total score (0-100) per subject, separate from the
    teacher-entered Grade model which stores component scores.
    """
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='lms_grades',
        verbose_name='Student',
    )
    subject_name = models.CharField(max_length=255, verbose_name='Subject Name')
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lms_grades',
        verbose_name='Subject (linked)',
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lms_grades',
        verbose_name='Group',
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lms_grades',
        verbose_name='Semester',
    )
    curriculum_semester = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Curriculum Semester',
        help_text='Semester number from the specialty curriculum (1–8).',
    )
    total_score = models.FloatField(null=True, blank=True, verbose_name='Total Score (0-100)')
    credits = models.IntegerField(default=0, verbose_name='Credits')
    import_source = models.CharField(max_length=100, blank=True, null=True, verbose_name='Import Source (sheet name)')

    class Meta:
        unique_together = ('student', 'subject_name', 'semester')
        verbose_name = 'LMS Grade'
        verbose_name_plural = 'LMS Grades'
        ordering = ['student', 'subject_name']

    def __str__(self):
        return f"{self.student} — {self.subject_name}: {self.total_score}"


class LMSImportLog(models.Model):
    """Tracks each LMS Excel import run."""
    imported_at = models.DateTimeField(auto_now_add=True, verbose_name='Imported At')
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Imported By',
    )
    filename = models.CharField(max_length=255, verbose_name='File Name')
    sheet_name = models.CharField(max_length=100, verbose_name='Sheet Name')
    rows_processed = models.IntegerField(default=0, verbose_name='Rows Processed')
    rows_created = models.IntegerField(default=0, verbose_name='Rows Created')
    rows_updated = models.IntegerField(default=0, verbose_name='Rows Updated')
    rows_skipped = models.IntegerField(default=0, verbose_name='Rows Skipped')
    errors = models.TextField(blank=True, null=True, verbose_name='Errors')

    class Meta:
        ordering = ['-imported_at']
        verbose_name = 'LMS Import Log'
        verbose_name_plural = 'LMS Import Logs'

    def __str__(self):
        return f"Import {self.filename} / {self.sheet_name} at {self.imported_at:%Y-%m-%d %H:%M}"
