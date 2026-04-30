from django.contrib import admin
from .models import Evaluation, EvaluationSettings

@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ['student', 'teacher_assignment', 'rating', 'created_at']
    list_filter = ['rating', 'created_at', 'teacher_assignment__teacher']
    search_fields = [
        'student__user__first_name', 
        'student__user__last_name',
        'teacher_assignment__teacher__first_name',
        'teacher_assignment__teacher__last_name',
        'teacher_assignment__subject__name'
    ]
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'

@admin.register(EvaluationSettings)
class EvaluationSettingsAdmin(admin.ModelAdmin):
    list_display = ['is_active', 'semester']