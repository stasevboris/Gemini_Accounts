"""Paged project text, Word and PDF readers; document contents remain untrusted."""
import hashlib
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from backend import AccountError

MAX_BYTES = 50 * 1024 * 1024


def file_bytes(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise AccountError('Choose a project file smaller than 50 MB.')
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise AccountError('The project file grew beyond 50 MB.')
    return raw


def document_text(path, raw):
    suffix = Path(path).suffix.lower()
    if suffix == '.docx':
        try:
            import io
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names = ['word/document.xml'] + sorted(n for n in archive.namelist()
                    if n.startswith(('word/header', 'word/footer', 'word/footnotes', 'word/endnotes')) and n.endswith('.xml'))
                total, sections = 0, []
                for name in names:
                    entry = archive.getinfo(name)
                    total += entry.file_size
                    if total > MAX_BYTES:
                        raise AccountError('Expanded Word document exceeds 50 MB.')
                    root = ET.fromstring(archive.read(name))
                    ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
                    paragraphs = [''.join(p.itertext()) if not p.findall('.//' + ns + 't') else
                                  ''.join(n.text or '' for n in p.iter(ns + 't')) for p in root.iter(ns + 'p')]
                    sections.append('\n'.join(paragraphs))
                return '\n\n'.join(sections)
        except (zipfile.BadZipFile, KeyError, ET.ParseError):
            raise AccountError('Cannot extract this Word document. Use a valid DOCX file.') from None
    if suffix in ('.doc', '.odt', '.rtf', '.pdf'):
        raise AccountError('For PDF use read_document with page numbers. Convert legacy Word/ODT/RTF to DOCX or text.')
    try:
        if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
            return raw.decode('utf-16')
        if b'\x00' in raw[:8192]:
            raise AccountError('This file is binary. Use the appropriate document reader.')
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            return raw.decode('cp1251')
        except UnicodeDecodeError:
            raise AccountError('Unsupported text encoding. Save the file as UTF-8.') from None


def integer(value, minimum, maximum, label):
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise AccountError('Invalid ' + label + '.')
    return value


def read_text(path, start_line=1, max_lines=200):
    start_line = integer(start_line, 1, 100000000, 'start_line')
    max_lines = integer(max_lines, 1, 2000, 'max_lines')
    raw = file_bytes(path)
    lines = document_text(path, raw).splitlines()
    selected, size = [], 0
    end = min(len(lines), start_line - 1 + max_lines)
    for index in range(start_line - 1, end):
        line = lines[index]
        if len(line) > 30000:
            raise AccountError('This line is longer than 30,000 characters. Use read_text_chunk with character offsets.')
        if selected and size + len(line) > 30000:
            break
        selected.append(line)
        size += len(line) + 1
    next_line = start_line + len(selected)
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'start_line': start_line,
            'end_line': next_line - 1, 'total_lines': len(lines), 'text': '\n'.join(selected),
            'next_line': next_line if next_line <= len(lines) else None}


def read_chunk(path, offset=0, max_chars=24000):
    offset = integer(offset, 0, 100000000, 'offset')
    max_chars = integer(max_chars, 1, 30000, 'max_chars')
    raw = file_bytes(path)
    text = document_text(path, raw)
    end = min(len(text), offset + max_chars)
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'offset': offset, 'total_chars': len(text),
            'text': text[offset:end], 'next_offset': end if end < len(text) else None}


def read_document(path, start_page=1, max_pages=3, offset=0):
    start_page = integer(start_page, 1, 10000000, 'start_page')
    max_pages = integer(max_pages, 1, 20, 'max_pages')
    offset = integer(offset, 0, 100000000, 'offset')
    if Path(path).suffix.lower() != '.pdf':
        return read_chunk(path, offset)
    from pypdf import PdfReader
    import io
    raw = file_bytes(path)
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted and not reader.decrypt(''):
            raise AccountError('The PDF requires a password. Supply an unlocked project copy.')
        count = len(reader.pages)
        output, used = [], 0
        next_page, next_offset = None, 0
        for number in range(start_page, min(count + 1, start_page + max_pages)):
            text = reader.pages[number - 1].extract_text() or ''
            begin = offset if number == start_page else 0
            available = 30000 - used
            part = text[begin:begin + available]
            output.append({'page': number, 'text': part})
            used += len(part)
            if begin + len(part) < len(text):
                next_page, next_offset = number, begin + len(part)
                break
            if number < count:
                next_page = number + 1
            else:
                next_page = None
            if used >= 30000:
                break
        return {'sha256': hashlib.sha256(raw).hexdigest(), 'total_pages': count, 'pages': output,
                'next_page': next_page, 'next_offset': next_offset,
                'note': 'No extractable text may indicate a scanned page requiring OCR.' if not used else ''}
    except AccountError:
        raise
    except Exception:
        raise AccountError('Cannot extract this PDF. Use a readable PDF or text copy.') from None
