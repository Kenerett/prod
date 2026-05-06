import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('school', '0007_add_lms_models_and_indexes'),
    ]

    operations = [
        # 1. Specialty
        migrations.CreateModel(
            name='Specialty',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=50, unique=True, verbose_name='Specialty Code')),
                ('name', models.CharField(max_length=200, verbose_name='Specialty Name')),
            ],
            options={
                'verbose_name': 'Specialty',
                'verbose_name_plural': 'Specialties',
                'ordering': ['name'],
            },
        ),

        # 2. Subject.code
        migrations.AddField(
            model_name='subject',
            name='code',
            field=models.CharField(
                blank=True, max_length=20, null=True, unique=True,
                verbose_name='Subject Code',
            ),
        ),

        # 3. Subject.name max_length 100→200 (backward-compatible)
        migrations.AlterField(
            model_name='subject',
            name='name',
            field=models.CharField(max_length=200, unique=True),
        ),

        # 4. Group.specialty FK
        migrations.AddField(
            model_name='group',
            name='specialty',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='groups',
                to='school.specialty',
                verbose_name='Specialty',
            ),
        ),

        # 5. CurriculumEntry
        migrations.CreateModel(
            name='CurriculumEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('semester_number', models.PositiveIntegerField(verbose_name='Semester Number')),
                ('subject_code', models.CharField(max_length=20, verbose_name='Subject Code')),
                ('subject_name', models.CharField(max_length=255, verbose_name='Subject Name')),
                ('ects', models.PositiveIntegerField(default=0, verbose_name='ECTS Credits')),
                ('hours_per_week', models.PositiveIntegerField(default=0, verbose_name='Hours/Week')),
                ('prerequisite_codes', models.JSONField(
                    blank=True,
                    default=list,
                    verbose_name='Prerequisite Codes',
                    help_text='List of subject codes that must be passed before this one.',
                )),
                ('specialty', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='curriculum_entries',
                    to='school.specialty',
                    verbose_name='Specialty',
                )),
                ('subject', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='curriculum_entries',
                    to='school.subject',
                    verbose_name='Subject (linked)',
                )),
            ],
            options={
                'verbose_name': 'Curriculum Entry',
                'verbose_name_plural': 'Curriculum Entries',
                'ordering': ['specialty', 'semester_number', 'subject_code'],
                'unique_together': {('specialty', 'subject_code')},
            },
        ),

        # 6. LMSGrade.curriculum_semester
        migrations.AddField(
            model_name='lmsgrade',
            name='curriculum_semester',
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name='Curriculum Semester',
                help_text='Semester number from the specialty curriculum (1–8).',
            ),
        ),
    ]
