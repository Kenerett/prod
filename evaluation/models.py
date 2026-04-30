from django.db import models
from school.models import TeacherAssignment, StudentProfile, Semester

class Evaluation(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    teacher_assignment = models.ForeignKey(TeacherAssignment, on_delete=models.CASCADE)
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 11)])  # 1-10 баллов
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('student', 'teacher_assignment')
        verbose_name = 'Evaluation'
        verbose_name_plural = 'Evaluations'
    
    def __str__(self):
        return f"{self.student.user.get_full_name()} → {self.teacher_assignment.teacher.get_full_name()} ({self.rating}/10)"

class EvaluationSettings(models.Model):
    is_active = models.BooleanField(default=True)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, null=True, blank=True)
    
    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
    
    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj
    
    def __str__(self):
        if self.semester:
            return f"Evaluation Settings (Active: {self.is_active}, Semester: {self.semester})"
        return f"Evaluation Settings (Active: {self.is_active})"