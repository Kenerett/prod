from django import forms
import pandas as pd
from django.http import HttpResponse




def download_template(self, request):
    data = {
        'Имя': ['Иван', 'Мария', 'Алексей'],
        'Фамилия': ['Петров', 'Сидорова', 'Козлов'],
        'Отчество': ['Сергеевич', 'Александровна', ''],
        'Логин': ['ivan.petrov', 'maria.sidorova', 'alexey.kozlov'],
        'Пароль': ['student123', 'password456', ''],
        'activity': [None, None, None],
        'midterm': [None, None, None],
        'SG1': [None, None, None],
        'SG2': [None, None, None],
        'final': [None, None, None],
        'total': [None, None, None],
    }
    df = pd.DataFrame(data)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="шаблон_студенты_с_оценками.xlsx"'

    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Students')

    return response