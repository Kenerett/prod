"""
Curriculum helpers: subject-name matching, specialty detection, prerequisite checks.
"""

import re
from difflib import SequenceMatcher


# ── Name normalisation ────────────────────────────────────────────────────────

_ROMAN_MAP = [
    (r'\bviii\b', '8'), (r'\bvii\b', '7'), (r'\bvi\b', '6'),
    (r'\biv\b', '4'),   (r'\biii\b', '3'), (r'\bii\b', '2'),
    (r'\bix\b', '9'),   (r'\bxi\b', '11'),(r'\bxii\b', '12'),
    (r'\bx\b', '10'),   (r'\bv\b', '5'),   (r'\bi\b', '1'),
]


def normalize(name: str) -> str:
    """Lowercase, strip, collapse whitespace, convert Roman numerals to digits."""
    name = name.strip().lower()
    for pattern, repl in _ROMAN_MAP:
        name = re.sub(pattern, repl, name)
    return re.sub(r'\s+', ' ', name)


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


# ── Curriculum entry lookup ───────────────────────────────────────────────────

def _sorted_words(name: str) -> str:
    """Normalize and sort words for word-order-independent comparison."""
    return ' '.join(sorted(normalize(name).split()))


def find_curriculum_entry(subject_name: str, specialty=None, threshold: float = 0.82):
    """
    Return the best-matching CurriculumEntry for *subject_name*.
    If *specialty* is given, search is restricted to that specialty.
    Tries exact, sequence-ratio, and word-sorted-ratio matching.
    Returns None if no entry exceeds *threshold*.
    """
    from school.models import CurriculumEntry

    qs = CurriculumEntry.objects.all()
    if specialty is not None:
        qs = qs.filter(specialty=specialty)

    norm      = normalize(subject_name)
    norm_sort = _sorted_words(subject_name)
    best_entry, best_ratio = None, 0.0

    for entry in qs:
        entry_norm = normalize(entry.subject_name)
        if norm == entry_norm:
            return entry
        ratio = SequenceMatcher(None, norm, entry_norm).ratio()
        # Also try word-sorted comparison to handle reorderings like
        # "History of Azerbaijan" ↔ "Azerbaijan History"
        sorted_ratio = SequenceMatcher(None, norm_sort, _sorted_words(entry.subject_name)).ratio()
        ratio = max(ratio, sorted_ratio)
        if ratio > best_ratio:
            best_ratio, best_entry = ratio, entry

    return best_entry if best_ratio >= threshold else None


# ── Specialty detection ───────────────────────────────────────────────────────

def detect_specialty(subject_names: list, threshold: float = 0.82):
    """
    Given a list of subject names from an Excel grade sheet, return the
    Specialty whose curriculum best covers those subjects.

    Returns (Specialty | None, match_count).
    """
    from school.models import Specialty

    specialties = list(Specialty.objects.prefetch_related('curriculum_entries'))
    if not specialties:
        return None, 0

    best_specialty, best_count = None, 0

    for specialty in specialties:
        entries = list(specialty.curriculum_entries.all())
        entry_norms = [normalize(e.subject_name) for e in entries]

        count = 0
        for name in subject_names:
            name_norm = normalize(name)
            if name_norm in entry_norms:
                count += 1
            elif any(
                SequenceMatcher(None, name_norm, en).ratio() >= threshold
                for en in entry_norms
            ):
                count += 1

        if count > best_count:
            best_count, best_specialty = count, specialty

    return best_specialty, best_count


# ── Prerequisite check ────────────────────────────────────────────────────────

PASSING_SCORE = 50


def can_enroll(student_profile, curriculum_entry):
    """
    Check whether *student_profile* has passed all prerequisites for
    *curriculum_entry*.

    Returns (ok: bool, missing: list[str])
      ok=True  → student may enrol
      ok=False → missing contains human-readable descriptions of unmet prereqs
    """
    from django.db.models import Q
    from school.models import LMSGrade, CurriculumEntry as CE

    prereq_codes = [
        c for c in (curriculum_entry.prerequisite_codes or [])
        if c and c.upper() != 'NONE'
    ]
    if not prereq_codes:
        return True, []

    missing = []
    for code in prereq_codes:
        prereq = CE.objects.filter(
            specialty=curriculum_entry.specialty,
            subject_code=code,
        ).first()
        if prereq is None:
            continue  # unknown prereq code — don't block

        passed = LMSGrade.objects.filter(
            student=student_profile,
            total_score__gte=PASSING_SCORE,
        ).filter(
            Q(subject_name__iexact=prereq.subject_name)
            | Q(subject__code__iexact=code)
        ).exists()

        if not passed:
            missing.append(f"{code}: {prereq.subject_name}")

    return len(missing) == 0, missing


# ── Bulk-link CurriculumEntry → Subject ──────────────────────────────────────

def link_curriculum_subjects(specialty=None):
    """
    For every CurriculumEntry that has no linked Subject, try to find or create
    a matching Subject by name/code and link it.
    Returns number of entries updated.
    """
    from school.models import CurriculumEntry, Subject

    qs = CurriculumEntry.objects.filter(subject__isnull=True)
    if specialty:
        qs = qs.filter(specialty=specialty)

    updated = 0
    for entry in qs:
        subj = (
            Subject.objects.filter(code__iexact=entry.subject_code).first()
            or Subject.objects.filter(name__iexact=entry.subject_name).first()
        )
        if subj is None:
            subj = Subject.objects.create(
                name=entry.subject_name,
                code=entry.subject_code,
                credits=entry.ects,
            )
        entry.subject = subj
        entry.save(update_fields=['subject'])
        updated += 1

    return updated
