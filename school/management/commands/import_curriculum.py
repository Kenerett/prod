"""
Management command: import_curriculum

Reads a .docx or .pdf curriculum file and populates Specialty + CurriculumEntry.

Usage:
    python manage.py import_curriculum --file /path/to/curriculum.docx \
        --specialty-code 50629 --specialty-name "Mechatronics"

Supported file formats:
  .docx  — Word document with semester paragraphs + tables
  .pdf   — PDF with the same ZU curriculum layout (pdfplumber required)

Both formats expect:
  - Text markers like "1st SEMESTER", "2nd SEMESTER", ...
  - Tables with columns: CODE | COURSE NAME | ECTS | HOURS | Prerequisites
"""

import re

from django.core.management.base import BaseCommand, CommandError

from school.models import Specialty, CurriculumEntry, Subject
from school.services.curriculum import link_curriculum_subjects


# Matches "1st SEMESTER", "2nd SEMESTER", "I. SEMESTER", "IV. SEMESTER",
# "FIRST YEAR I. SEMESTER", "SEMESTER I", etc.
_SEMESTER_RE = re.compile(
    r'(\d+)(?:st|nd|rd|th)\s+semester'
    r'|([IVX]{1,4})\.\s*semester'
    r'|semester\s+([IVX]{1,4}|\d+)',
    re.IGNORECASE,
)

# Stop parsing when these words appear — rest of document is module descriptions
_STOP_RE = re.compile(
    r'appendix|module description|course description|syllabus|learning outcome',
    re.IGNORECASE,
)

_ROMAN = {'I':1,'II':2,'III':3,'IV':4,'V':5,'VI':6,'VII':7,'VIII':8,'IX':9,'X':10}


def _roman(s: str) -> int | None:
    return _ROMAN.get(s.upper().strip())


def _parse_prereqs(raw: str) -> list[str]:
    """Parse prerequisite cell → list of codes. Fixes PDF newlines inside codes."""
    if not raw:
        return []
    raw = raw.replace('\n', ' ')
    parts = re.split(r'[,;/]+', raw)
    return [p.strip() for p in parts if p.strip() and p.strip().upper() not in ('NONE', '')]


def _detect_cols(header_row: list) -> dict:
    """
    Given a table header row, return mapping:
      {'code': idx, 'name': idx, 'ects': idx, 'hours': idx, 'prereq': idx|None}
    'prereq' is None when no prerequisite column is found in the header.
    """
    cols = {'prereq': None}   # None = no prereq column detected
    for i, cell in enumerate(header_row):
        c = (cell or '').upper().replace('\n', ' ')
        if re.search(r'\bcode\b|\bcodes\b', c, re.IGNORECASE):
            cols.setdefault('code', i)
        elif re.search(r'course|name', c, re.IGNORECASE):
            cols.setdefault('name', i)
        elif re.search(r'\bects\b|\bcredit', c, re.IGNORECASE):
            cols.setdefault('ects', i)
        elif re.search(r'\bhour', c, re.IGNORECASE):
            cols.setdefault('hours', i)
        elif re.search(r'prereq|prerequisit', c, re.IGNORECASE):
            cols['prereq'] = i   # always override — explicit keyword wins
    # positional fallbacks (not for prereq — must be explicit)
    cols.setdefault('code',  0)
    cols.setdefault('name',  1)
    cols.setdefault('ects',  2)
    cols.setdefault('hours', 4)
    return cols


def _find_semesters_in_text(text: str) -> list[int]:
    """Return all semester numbers (1-8) found in text, in order of appearance."""
    result = []
    for m in _SEMESTER_RE.finditer(text):
        g1, g2, g3 = m.group(1), m.group(2), m.group(3)
        if g1:
            v = int(g1)
        elif g2:
            v = _roman(g2)
        elif g3:
            v = _roman(g3) or (int(g3) if g3.isdigit() else None)
        else:
            continue
        if v and 1 <= v <= 8:   # ignore "SEMESTER 30" / "SEMESTER CREDITS"
            result.append(v)
    return result


def _parse_table_rows(table: list, cols: dict, current_semester: int) -> list[dict]:
    """Extract curriculum rows from a raw pdfplumber/docx table."""
    rows = []
    for row in table:
        if not row:
            continue
        def cell(i):
            v = row[i] if i < len(row) else None
            return (v or '').strip().replace('\n', ' ')

        code = cell(cols['code'])
        name = cell(cols['name'])

        if not code or code.upper() in ('CODE', 'CODES'):
            continue
        if not name or re.search(r'^course\s*(name)?$', name, re.IGNORECASE):
            continue
        if re.search(r'\bTOTAL\b', name, re.IGNORECASE) or re.search(r'\bTOTAL\b', code, re.IGNORECASE):
            continue
        if re.search(r'\bELECTIVE\b', name, re.IGNORECASE) and not code.strip():
            continue

        ects_raw   = cell(cols['ects'])
        prereq_raw = cell(cols['prereq']) if cols.get('prereq') is not None else ''
        hours_raw  = cell(cols['hours'])

        try:
            ects = int(re.search(r'\d+', ects_raw).group()) if re.search(r'\d+', ects_raw) else 0
        except Exception:
            ects = 0
        try:
            hours = int(re.search(r'\d+', hours_raw).group()) if re.search(r'\d+', hours_raw) else 0
        except Exception:
            hours = 0

        rows.append({
            'semester':      current_semester,
            'code':          code,
            'name':          name,
            'ects':          ects,
            'hours':         hours,
            'prerequisites': _parse_prereqs(prereq_raw),
        })
    return rows


# ── DOCX parser ───────────────────────────────────────────────────────────────

def _parse_docx(path: str) -> list[dict]:
    try:
        import docx
    except ImportError:
        raise CommandError("python-docx is required: pip install python-docx")

    doc = docx.Document(path)
    rows = []
    current_semester = None
    table_iter = iter(doc.tables)

    for block in _iter_blocks(doc):
        if block['type'] == 'paragraph':
            text = block['text']
            if _STOP_RE.search(text):
                break
            nums = _find_semesters_in_text(text)
            if nums:
                current_semester = nums[-1]
        elif block['type'] == 'table':
            table = next(table_iter)
            if current_semester is None:
                continue
            raw = [c.text.strip() for c in table.rows[0].cells] if table.rows else []
            cols = _detect_cols(raw)
            raw_rows = [[c.text.strip() for c in row.cells] for row in table.rows[1:]]
            rows.extend(_parse_table_rows(raw_rows, cols, current_semester))

    return rows


def _iter_blocks(doc):
    """Yield paragraph/table blocks in document order."""
    body = doc.element.body
    for child in body:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag == 'p':
            text = ''.join(
                n.text or ''
                for n in child.iter(
                    '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'
                )
            )
            yield {'type': 'paragraph', 'text': text}
        elif tag == 'tbl':
            yield {'type': 'table'}


# ── PDF parser ────────────────────────────────────────────────────────────────

def _parse_pdf(path: str) -> list[dict]:
    try:
        import pdfplumber
    except ImportError:
        raise CommandError("pdfplumber is required: pip install pdfplumber")

    rows = []
    current_semester = None

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text   = page.extract_text() or ''

            # Stop at appendices / module descriptions
            if _STOP_RE.search(text):
                break

            tables = page.extract_tables()

            # Find semester numbers in this page's text (in appearance order)
            sem_on_page = _find_semesters_in_text(text)

            # If the page begins with a table header (not a semester marker),
            # the first table continues the previous semester.
            # Example: page ends mid-semester, table starts before next marker.
            first_line = text.strip().split('\n')[0].upper()
            page_starts_with_table = bool(
                re.search(r'\bcode\b|\bcourse\b', first_line, re.IGNORECASE)
            )
            # Offset: how many markers to skip for the first table on this page
            marker_offset = 0 if not page_starts_with_table else -1

            for ti, table in enumerate(tables):
                if not table:
                    continue

                marker_idx = ti + marker_offset
                if 0 <= marker_idx < len(sem_on_page):
                    current_semester = sem_on_page[marker_idx]
                elif sem_on_page and marker_idx >= len(sem_on_page):
                    current_semester = sem_on_page[-1]
                # else: marker_idx < 0 → keep current_semester from previous page

                if current_semester is None:
                    continue

                # Auto-detect columns from header row
                header = [str(c or '').strip() for c in table[0]] if table else []
                cols = _detect_cols(header)
                rows.extend(_parse_table_rows(table[1:], cols, current_semester))

            # Carry forward the LAST semester marker seen on this page,
            # even if its table starts on the next page.
            if sem_on_page:
                current_semester = sem_on_page[-1]

    return rows


# ── Dispatcher ────────────────────────────────────────────────────────────────

def parse_curriculum_file(path: str) -> list[dict]:
    """Parse .docx or .pdf curriculum file. Returns list of row dicts."""
    lower = path.lower()
    if lower.endswith('.pdf'):
        return _parse_pdf(path)
    elif lower.endswith('.docx'):
        return _parse_docx(path)
    else:
        raise CommandError(f"Unsupported file format: {path}. Use .docx or .pdf")


# ── Management command ────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Import curriculum from a .docx or .pdf file into Specialty + CurriculumEntry models.'

    def add_arguments(self, parser):
        parser.add_argument('--file',           required=True,
                            help='Path to .docx or .pdf file')
        parser.add_argument('--specialty-code', required=True,
                            help='Specialty code (e.g. 50629)')
        parser.add_argument('--specialty-name', required=True,
                            help='Specialty name (e.g. Mechatronics)')
        parser.add_argument('--clear',          action='store_true',
                            help='Delete existing entries for this specialty before import')
        parser.add_argument('--link-subjects',  action='store_true',
                            help='Create/link Subject objects after import')

    def handle(self, *args, **options):
        path      = options['file']
        spec_code = options['specialty_code']
        spec_name = options['specialty_name']
        do_clear  = options['clear']
        do_link   = options['link_subjects']

        self.stdout.write(f"Parsing {path} …")
        rows = parse_curriculum_file(path)
        self.stdout.write(f"  Found {len(rows)} curriculum rows.")

        try:
            specialty = Specialty.objects.get(code=spec_code)
        except Specialty.DoesNotExist:
            raise CommandError(
                f"Specialty with code '{spec_code}' does not exist. "
                f"Please create it in the admin panel first."
            )
        self.stdout.write(f"  Found specialty: {specialty}")

        if do_clear:
            deleted, _ = CurriculumEntry.objects.filter(specialty=specialty).delete()
            self.stdout.write(f"  Cleared {deleted} existing entries.")

        created_cnt = updated_cnt = 0
        for row in rows:
            if not row['name']:
                continue
            base_code = row['code'] or f"__AUTO_{row['name'][:10].replace(' ', '_').upper()}"
            # If this code already belongs to a DIFFERENT subject, make the code unique.
            code = base_code
            suffix = 2
            while True:
                existing = CurriculumEntry.objects.filter(
                    specialty=specialty, subject_code=code,
                ).exclude(subject_name__iexact=row['name']).first()
                if existing is None:
                    break
                code = f"{base_code}_{suffix}"
                suffix += 1

            _, was_created = CurriculumEntry.objects.update_or_create(
                specialty=specialty,
                subject_code=code,
                defaults={
                    'semester_number':    row['semester'],
                    'subject_name':       row['name'],
                    'ects':               row['ects'],
                    'hours_per_week':     row['hours'],
                    'prerequisite_codes': row['prerequisites'],
                },
            )
            if was_created:
                created_cnt += 1
            else:
                updated_cnt += 1

        self.stdout.write(self.style.SUCCESS(
            f"  Entries: {created_cnt} created, {updated_cnt} updated."
        ))

        if do_link:
            linked = link_curriculum_subjects(specialty=specialty)
            self.stdout.write(self.style.SUCCESS(f"  Linked {linked} Subject objects."))
