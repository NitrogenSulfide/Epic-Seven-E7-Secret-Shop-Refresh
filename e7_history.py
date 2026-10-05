"""Versioned session records, lossless legacy CSV migration and Excel export."""
from collections import deque
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import tempfile
import uuid
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

FIELDS = ['Session ID', 'Started at', 'Control mode', 'Mode', 'Outcome', 'Reason',
          'Duration', 'Skystone spent', 'Gold spent', 'Covenant bookmark', 'Mystic medal',
          'Friendship bookmark', 'Legacy extra fields']
NUMERIC_FIELDS = {'Duration', 'Skystone spent', 'Gold spent', 'Covenant bookmark',
                  'Mystic medal', 'Friendship bookmark'}
LEGACY_FIELDS = ['Duration', 'Skystone spent', 'Gold spent', 'Covenant bookmark', 'Mystic medal']


def history_mode(row, fieldnames):
    if row.get('Mode'):
        return row['Mode']
    if 'Friendship bookmark' in fieldnames:
        return 'Debug' if row.get('Friendship bookmark') is not None else 'Normal'
    if fieldnames == LEGACY_FIELDS:
        extra = row.get(None, [])
        if len(extra) == 1 and str(extra[0]).isdigit():
            return 'Debug'
        if not extra:
            return 'Normal'
    return 'Unknown'


def _normalize(row, fieldnames):
    record = {key: value for key, value in row.items() if key is not None}
    record['Mode'] = history_mode(row, fieldnames)
    record.setdefault('Control mode', 'Unknown')
    record.setdefault('Outcome', 'Unknown (legacy)')
    extra = row.get(None, [])
    if extra:
        record['Legacy extra fields'] = json.dumps(extra)
        if fieldnames == LEGACY_FIELDS and len(extra) == 1 and str(extra[0]).isdigit():
            record['Friendship bookmark'] = extra[0]
    return record


def read_sessions(path, limit=None):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream, strict=True)
        fields = reader.fieldnames or []
        records = (_normalize(row, fields) for row in reader)
        return list(deque(records, maxlen=limit)) if limit is not None else list(records)


def append_session(path, record):
    """Replace atomically; preserve old bytes once before changing their schema."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = read_sessions(path)
    if record.get('Session ID') and any(row.get('Session ID') == record['Session ID'] for row in rows):
        return
    fields = list(FIELDS)
    for row in rows:
        fields.extend(key for key in row if key not in fields)
    old_header = []
    if path.exists():
        with path.open(newline='', encoding='utf-8-sig') as stream:
            old_header = next(csv.reader(stream), [])
    rows.append(record)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', newline='', encoding='utf-8',
                                         dir=path.parent, suffix='.csv.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        if old_header and old_header != fields:
            backup = path.parent / 'schema-backups'
            backup.mkdir(exist_ok=True)
            (backup / f'{path.stem}-{uuid.uuid4().hex}.csv').write_bytes(path.read_bytes())
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def new_session_metadata(control_mode, calibration=False):
    return {'Session ID': uuid.uuid4().hex,
            'Started at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'Control mode': control_mode, 'Mode': 'Debug' if calibration else 'Normal'}


def _column(number):
    result = ''
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def export_sessions(path, records):
    """Write a real .xlsx using the standard library; text cannot become formulas."""
    fields = list(FIELDS)
    for record in records:
        fields.extend(key for key in record if key not in fields)
    if len(records) > 1_048_573:
        raise ValueError('Too many sessions for one Excel sheet.')
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    ET.register_namespace('', ns)
    def node(parent, name, **attributes):
        return ET.SubElement(parent, f'{{{ns}}}{name}', attributes)
    sheet = ET.Element(f'{{{ns}}}worksheet')
    views = node(sheet, 'sheetViews')
    view = node(views, 'sheetView', workbookViewId='0')
    node(view, 'pane', ySplit='1', topLeftCell='A2', activePane='bottomLeft', state='frozen')
    columns = node(sheet, 'cols')
    for index, field in enumerate(fields, 1):
        width = 48 if field == 'Reason' else 28 if field in ('Started at', 'Session ID') else 21
        node(columns, 'col', min=str(index), max=str(index), width=str(width), customWidth='1')
    data = node(sheet, 'sheetData')
    def text_cell(row, address, value, style='0'):
        cell = node(row, 'c', r=address, t='inlineStr', s=style)
        text = node(node(cell, 'is'), 't')
        # XML 1.0 cannot represent control characters from a diagnostic reason.
        text.text = ''.join(char for char in str(value or '') if ord(char) >= 32 or char in '\t\n\r')
        text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    header = node(data, 'row', r='1')
    for index, field in enumerate(fields, 1):
        text_cell(header, f'{_column(index)}1', 'Duration (seconds)' if field == 'Duration' else
                  'Started at (UTC)' if field == 'Started at' else field, '1')
    totals = {key: 0 for key in NUMERIC_FIELDS}
    for row_index, record in enumerate(records, 2):
        row = node(data, 'row', r=str(row_index))
        for index, field in enumerate(fields, 1):
            address = f'{_column(index)}{row_index}'
            value = record.get(field, '')
            try:
                number = float(value) if field in NUMERIC_FIELDS and value not in ('', None) else None
            except (TypeError, ValueError):
                number = None
            if number is not None and math.isfinite(number):
                cell = node(row, 'c', r=address, t='n', s='3' if field == 'Duration' else '2')
                node(cell, 'v').text = str(number)
                totals[field] += number
            else:
                text_cell(row, address, value)
    last = len(records) + 1
    node(sheet, 'autoFilter', ref=f'A1:{_column(len(fields))}{last}')
    if records:
        row = node(data, 'row', r=str(last + 1))
        text_cell(row, f'A{last + 1}', 'Totals', '1')
        for index, field in enumerate(fields, 1):
            if field in NUMERIC_FIELDS:
                cell = node(row, 'c', r=f'{_column(index)}{last + 1}', s='3' if field == 'Duration' else '2')
                node(cell, 'f').text = f'SUM({_column(index)}2:{_column(index)}{last})'
                node(cell, 'v').text = str(totals[field])
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sessions" sheetId="1" r:id="rId1"/></sheets><calcPr calcId="0" fullCalcOnLoad="1"/></workbook>',
        'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        'xl/styles.xml': '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/><color rgb="FFFFFFFF"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF2563EB"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0"/><xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
        'xl/worksheets/sheet1.xml': ET.tostring(sheet, encoding='utf-8', xml_declaration=True),
    }
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.xlsx.tmp', delete=False) as stream:
            temporary = Path(stream.name)
        with ZipFile(temporary, 'w', ZIP_DEFLATED) as archive:
            for name, content in parts.items():
                archive.writestr(name, content)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
