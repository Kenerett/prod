from django import forms
from .models import Evaluation

class EvaluationForm(forms.ModelForm):
    class Meta:
        model = Evaluation
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.Select(choices=[(i, i) for i in range(1, 11)]),
            'comment': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ваш комментарий (необязательно)'})
        }