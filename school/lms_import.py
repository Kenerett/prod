"""
LMS Excel import logic.

Expected Excel format:
  Sheet "Tələbə umumi məlumatlar" — full student info (Sheet 1)
  Other sheets (e.g. "ZU 044", "642.23E", "ZU 04.22") — grade tables:

  Standard format:
    Row 0: group_name | names_header   | subject1 | subject2 | ... | GPA | Total
    Row 1: (blank)    | "Credit"       | credits1 | credits2 | ...
    Row 2+: index     | Full Name      | score1   | score2   | ...

  Compact format (no index column):
    Row 0: group_name | subject1       | subject2 | ... | GPA | Total
    Row 1: "Credit"   | credits1       | credits2 | ...
    Row 2+: Full Name | score1         | score2   | ...

  Detection: if credits_row[1] is a number → compact; otherwise → standard.
"""

import logging
import re
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)

# ── Column mapping for Sheet 1 ────────────────────────────────────────────────
SHEET1_COLS = {
    'fin':             'FIN',
    'faculty':         'Fakültə adı',
    'group':           'Qrup adı/N-si',
    'specialty_code':  'ixtisas və  ixtisaslaşmanın kodu (NK qərarına əsasən)',
    'specialty_name':  'İxtrisasın adı (ingilis dilində)',
    'edu_form':        'Təhsil forması (Əyani/qiyabi) ',
    'edu_level':       'Təhsil pilləsi',
    'last_name':       'Soyadı',
    'first_name':      'Adı',
    'patronymic':      'Atasının adı',
    'dob':             'Anadan olma tarixi',
    'gender':          'Cinsi',
    'citizenship':     'Vətəndaşlıq',
    'birth_city':      'Anadan olduğu şəhər, rayon',
    'address':         'Yaşadığı ünvan',
    'phone':           'Əlaqə telefon N-si',
    'email':           'e-mail ünvanı',
    'status':          'Statusu\n(dövlət sifarişli və ya ödənişli)',
    'admission_year':  'Qəbul ili',
    'admission_score': 'Qəbul balı',
    'study_year':      'Təhsil ili (kurs)',
    'scholarship':     'Təqəüd alır (hə/yox)',
    'id_series':       'Şəxsiyyət vəsiqəsinin seriyası',
    'id_number':       'Şəxsiyyət vəsiqəsinin nömrəsi',
    'card_number':     'Tələbə kartının nömrəsi',
}


def _str(val):
    if pd.isna(val):
        return ''
    return str(val).strip()


def _float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _int(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _normalize_group(name: str) -> str:
    """Strip spaces, hyphens, dots, digits-only prefixes and upper-case for fuzzy matching."""
    return re.sub(r'[\s\-\.]', '', name).upper()


def _find_group_by_name(group_name: str):
    """
    Find an existing Group by name:
      1. Exact case-insensitive match
      2. Contains match
      3. Normalized match (strip spaces/hyphens/dots)
      4. One normalized name is a suffix of the other (handles "6006029 Mechatronics -ZU 045" → "ZU-045")
    Never creates a new group.
    """
    from school.models import Group

    g = Group.objects.filter(name__iexact=group_name).first()
    if g:
        return g

    g = Group.objects.filter(name__icontains=group_name).first()
    if g:
        return g

    norm = _normalize_group(group_name)
    best = None
    for candidate in Group.objects.all():
        cn = _normalize_group(candidate.name)
        if cn == norm:
            return candidate
        if norm.endswith(cn) or norm.startswith(cn) or cn.endswith(norm) or cn.startswith(norm):
            best = candidate

    return best


def _strip_teacher_suffix(name: str) -> str:
    """
    Remove teacher name appended after ' - ' or '- ' followed by an uppercase letter.
    E.g. "Technical English 1- Gulnara Ahmadova" → "Technical English 1"
         "Applied Physics - Nazıyev Ceyhun"       → "Applied Physics"
    """
    cleaned = re.sub(r'\s*-\s+(?=[A-ZÇƏĞIİŞÜÖa-z])', '\x00', name).split('\x00')[0]
    return cleaned.strip()


def _date(val):
    if pd.isna(val) or val == '':
        return None
    if isinstance(val, datetime):
        return val.date()
    try:
        return pd.to_datetime(str(val), dayfirst=True).date()
    except Exception:
        return None


def import_sheet1(df, semester=None):
    """
    Import student general info from Sheet 1.
    Returns dict: {created, updated, skipped, errors}
    """
    from school.models import (
        CustomUser, StudentProfile, StudentExtendedInfo, Group, Specialty,
    )

    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

    for idx, row in df.iterrows():
        last_name  = _str(row.get(SHEET1_COLS['last_name'], ''))
        first_name = _str(row.get(SHEET1_COLS['first_name'], ''))
        patronymic = _str(row.get(SHEET1_COLS['patronymic'], ''))
        email      = _str(row.get(SHEET1_COLS['email'], ''))
        fin        = _str(row.get(SHEET1_COLS['fin'], ''))
        group_name = _str(row.get(SHEET1_COLS['group'], ''))
        spec_code  = _str(row.get(SHEET1_COLS['specialty_code'], ''))
        spec_name  = _str(row.get(SHEET1_COLS['specialty_name'], ''))

        if not last_name or not first_name:
            stats['skipped'] += 1
            continue

        # ── Find or create user ───────────────────────────────────────────────
        username = fin if fin else f"{last_name.lower()}.{first_name.lower()}"
        username = username[:150]

        user = None
        if email:
            user = CustomUser.objects.filter(email__iexact=email).first()
        if user is None and fin:
            user = CustomUser.objects.filter(username__iexact=fin).first()

        created_user = False
        if user is None:
            user = CustomUser(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                middle_name=patronymic or None,
                role=CustomUser.STUDENT,
            )
            user.set_unusable_password()
            try:
                user.save()
                created_user = True
            except Exception as e:
                stats['errors'].append(f"Row {idx+2}: cannot create user '{username}': {e}")
                stats['skipped'] += 1
                continue
        else:
            changed = False
            if user.first_name != first_name:
                user.first_name = first_name
                changed = True
            if user.last_name != last_name:
                user.last_name = last_name
                changed = True
            if patronymic and user.middle_name != patronymic:
                user.middle_name = patronymic
                changed = True
            if changed:
                user.save(update_fields=['first_name', 'last_name', 'middle_name'])

        # ── Find or create StudentProfile ─────────────────────────────────────
        profile, _ = StudentProfile.objects.get_or_create(user=user)

        # ── Resolve specialty (never auto-create — must exist) ───────────────
        specialty = None
        if spec_code:
            specialty = Specialty.objects.filter(code=spec_code).first()

        # ── Find or create Group, link specialty ──────────────────────────────
        if group_name:
            group, _ = Group.objects.get_or_create(name=group_name)
            if specialty and group.specialty_id != specialty.pk:
                group.specialty = specialty
                group.save(update_fields=['specialty'])
            group.students.add(profile)

        # ── Create/update StudentExtendedInfo ─────────────────────────────────
        dob = _date(row.get(SHEET1_COLS['dob'], None))
        scholarship_raw = _str(row.get(SHEET1_COLS['scholarship'], ''))
        scholarship = scholarship_raw.lower() in ('hə', 'he', 'yes', 'true', '1', 'h')

        ext, ext_created = StudentExtendedInfo.objects.get_or_create(student=profile)
        ext.fin_code            = fin or ext.fin_code
        ext.faculty             = _str(row.get(SHEET1_COLS['faculty'], '')) or ext.faculty
        ext.specialty_code      = spec_code or ext.specialty_code
        ext.specialty_name      = spec_name or ext.specialty_name
        ext.education_form      = _str(row.get(SHEET1_COLS['edu_form'], '')) or ext.education_form
        ext.education_level     = _str(row.get(SHEET1_COLS['edu_level'], '')) or ext.education_level
        ext.date_of_birth       = dob or ext.date_of_birth
        ext.gender              = _str(row.get(SHEET1_COLS['gender'], '')) or ext.gender
        ext.citizenship         = _str(row.get(SHEET1_COLS['citizenship'], '')) or ext.citizenship
        ext.birth_city          = _str(row.get(SHEET1_COLS['birth_city'], '')) or ext.birth_city
        ext.address             = _str(row.get(SHEET1_COLS['address'], '')) or ext.address
        ext.phone               = _str(row.get(SHEET1_COLS['phone'], '')) or ext.phone
        ext.status              = _str(row.get(SHEET1_COLS['status'], '')) or ext.status
        ext.admission_year      = _int(row.get(SHEET1_COLS['admission_year'])) or ext.admission_year
        ext.admission_score     = _float(row.get(SHEET1_COLS['admission_score'])) or ext.admission_score
        ext.study_year          = _int(row.get(SHEET1_COLS['study_year'])) or ext.study_year
        ext.gets_scholarship    = scholarship
        ext.id_card_series      = _str(row.get(SHEET1_COLS['id_series'], '')) or ext.id_card_series
        ext.id_card_number      = _str(row.get(SHEET1_COLS['id_number'], '')) or ext.id_card_number
        ext.student_card_number = _str(row.get(SHEET1_COLS['card_number'], '')) or ext.student_card_number
        ext.save()

        if created_user or ext_created:
            stats['created'] += 1
        else:
            stats['updated'] += 1

    return stats


def import_grade_sheet(df_raw, sheet_name, semester=None):
    """
    Import cumulative grades from a grade sheet.

    Expected layout (no header, raw rows):
      Row 0: group_name | subject1 | subject2 | ... | GPA | Total
      Row 1: (blank)   | credits1  | credits2 | ... | ... | ...
      Row 2+: index    | Full Name | score1   | score2 | ... | gpa | total

    Automatically detects specialty from subject names and assigns curriculum
    semester numbers to each LMSGrade record.

    Returns dict: {created, updated, skipped, errors}
    """
    from school.models import StudentProfile, LMSGrade, Subject, Group
    from school.services.curriculum import detect_specialty, find_curriculum_entry

    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

    if df_raw.shape[0] < 3:
        stats['errors'].append("Sheet has fewer than 3 rows — cannot parse.")
        return stats

    header_row  = list(df_raw.iloc[0])
    credits_row = list(df_raw.iloc[1])

    group_name = _str(header_row[0]) if not pd.isna(header_row[0]) else sheet_name

    # ── Detect column layout ──────────────────────────────────────────────────
    # Compact: credits_row[1] is a number → subjects start at col 1, name at col 0
    # Standard: credits_row[1] is text/blank → subjects start at col 2, name at col 1
    col1_cred = _int(credits_row[1]) if len(credits_row) > 1 else None
    if col1_cred is not None:
        name_col   = 0
        subj_start = 1
    else:
        name_col   = 1
        subj_start = 2

    subject_cols = []  # (col_index, subject_name, credits)
    for col_idx in range(subj_start, len(header_row)):
        name = _strip_teacher_suffix(_str(header_row[col_idx]))
        if not name or name.lower() in ('gpa', 'total', ''):
            continue
        cred = _int(credits_row[col_idx]) or 0
        subject_cols.append((col_idx, name, cred))

    if not subject_cols:
        stats['errors'].append(f"No subject columns found in sheet '{sheet_name}'.")
        return stats

    # ── Detect specialty from subject names ───────────────────────────────────
    subject_names = [name for _, name, _ in subject_cols]
    specialty, match_count = detect_specialty(subject_names)
    if specialty:
        logger.info(
            "Sheet '%s': detected specialty '%s' (%d/%d subjects matched).",
            sheet_name, specialty.name, match_count, len(subject_names),
        )
    else:
        logger.warning("Sheet '%s': no specialty detected from %d subjects.", sheet_name, len(subject_names))

    # ── Pre-build a map: subject_name → curriculum_semester ──────────────────
    curriculum_sem_map: dict[str, int] = {}
    subject_obj_map:   dict[str, Subject | None] = {}
    for _, subj_name, _ in subject_cols:
        entry = find_curriculum_entry(subj_name, specialty=specialty)
        curriculum_sem_map[subj_name] = entry.semester_number if entry else None
        if entry and entry.subject_id:
            subject_obj_map[subj_name] = entry.subject
        else:
            subject_obj_map[subj_name] = Subject.objects.filter(
                name__iexact=subj_name
            ).first()

    # ── Find Group (never auto-create from grade sheets) ──────────────────────
    group = _find_group_by_name(group_name)
    if group is None:
        logger.warning(
            "Sheet '%s': group '%s' not found — grades imported without group.",
            sheet_name, group_name,
        )
    elif specialty and group.specialty_id != specialty.pk:
        group.specialty = specialty
        group.save(update_fields=['specialty'])

    # ── Process student rows ──────────────────────────────────────────────────
    for row_idx in range(2, df_raw.shape[0]):
        row = list(df_raw.iloc[row_idx])
        full_name = _str(row[name_col]) if len(row) > name_col else ''
        if not full_name or full_name.lower() == 'credit':
            stats['skipped'] += 1
            continue

        name_parts = full_name.split()
        profile = _find_student_profile(full_name, name_parts, group)

        if profile is None:
            stats['errors'].append(
                f"Sheet '{sheet_name}' row {row_idx + 1}: student not found — '{full_name}'"
            )
            stats['skipped'] += 1
            continue

        for col_idx, subject_name, credits in subject_cols:
            score = _float(row[col_idx]) if col_idx < len(row) else None
            if score is None:
                continue

            cur_sem = curriculum_sem_map.get(subject_name)
            subj_obj = subject_obj_map.get(subject_name)

            obj, created = LMSGrade.objects.update_or_create(
                student=profile,
                subject_name=subject_name,
                semester=semester,
                defaults={
                    'total_score':        score,
                    'credits':            credits,
                    'subject':            subj_obj,
                    'group':              group,
                    'import_source':      sheet_name,
                    'curriculum_semester': cur_sem,
                },
            )
            if created:
                stats['created'] += 1
            else:
                stats['updated'] += 1

    return stats


def _find_student_profile(full_name, name_parts, group=None):
    """
    Try to find a StudentProfile matching the given full name.
    Searches within the group first, then globally.
    """
    from school.models import StudentProfile

    def _qs():
        if group is not None:
            return StudentProfile.objects.filter(groups=group).select_related('user')
        return StudentProfile.objects.select_related('user')

    if len(name_parts) >= 2:
        qs = _qs().filter(
            user__last_name__iexact=name_parts[0],
            user__first_name__iexact=name_parts[1],
        )
        profile = qs.first()
        if profile:
            return profile

    for p in _qs():
        candidate = f"{p.user.last_name} {p.user.first_name}"
        if p.user.middle_name:
            candidate += f" {p.user.middle_name}"
        if candidate.strip().lower() == full_name.lower():
            return p

    if group is not None:
        return _find_student_profile(full_name, name_parts, group=None)

    return None


def detect_sheet_type(sheet_name, df_raw):
    """Return 'students' for sheet 1, 'grades' for grade sheets."""
    if 'məlumat' in sheet_name.lower() or 'umumi' in sheet_name.lower():
        return 'students'
    return 'grades'


def parse_excel(file_path_or_buffer):
    """
    Open Excel file and return list of (sheet_name, sheet_type, dataframe).
    """
    xl = pd.ExcelFile(file_path_or_buffer)
    result = []
    for sheet in xl.sheet_names:
        df_raw = pd.read_excel(xl, sheet_name=sheet, header=None)
        kind = detect_sheet_type(sheet, df_raw)
        if kind == 'students':
            df = pd.read_excel(xl, sheet_name=sheet, header=0)
        else:
            df = df_raw
        result.append((sheet, kind, df))
    return result
