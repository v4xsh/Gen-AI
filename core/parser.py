import re
import io
import docx
import pdfplumber


HEADING_KEYWORDS = [
    "whereas", "witnesseth", "now therefore", "definitions",
    "representations", "warranties", "covenants", "indemnification",
    "indemnity", "termination", "insurance", "confidentiality",
    "dispute", "general", "miscellaneous", "scope", "purpose",
    "consideration", "assignment", "waiver", "notices", "signatures"
]


def _detect_heading_level(text: str, style_name: str = None) -> int:
    """Detect heading level (1-6) or return 0 if not a heading."""
    text = text.strip()
    if not text or len(text) >= 120:
        return 0

    if style_name:
        s = style_name.lower()
        if s.startswith("heading"):
            try:
                return min(max(int(s.split()[-1]), 1), 6)
            except (ValueError, IndexError):
                return 1
        if s == "title":
            return 1
        if s == "subtitle":
            return 2

    if text.endswith(","):
        return 0

    m = re.match(
        r'^(article|section|clause|paragraph|exhibit|schedule|appendix)'
        r'\s+(I|V|X|L|C|D|M|[0-9]+)[\.:]?\s',
        text, re.IGNORECASE
    )
    if m:
        return 1

    m = re.match(
        r'^(article|section|clause|paragraph)\s+(\d+(?:\.\d+)+)\b',
        text, re.IGNORECASE
    )
    if m:
        depth = len(m.group(2).split("."))
        return min(depth, 6)

    if text.upper() == text and len(text) > 8:
        return 1

    m = re.match(r'^(\d+(?:\.\d+)*)\.?\s+\w', text)
    if m:
        depth = len(m.group(1).split("."))
        return min(depth, 6)

    if re.match(r'^[IVXLCDM]+\.\s+\w', text):
        return 1

    if re.match(r'^\(?[a-z]\)\s+\w', text):
        return 3

    if re.match(r'^(%s)\b' % '|'.join(HEADING_KEYWORDS), text, re.IGNORECASE):
        return 1

    return 0


def _build_hierarchy(elements: list) -> dict:
    """Build nested hierarchy tree from flat elements with .level fields."""
    root_sections = []
    preamble = []
    stack = []

    for el in elements:
        if el["type"] == "heading":
            level = el.get("level", 1)
            section = {
                "heading": el,
                "content": [],
                "subsections": []
            }
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1]["subsections"].append(section)
            else:
                root_sections.append(section)
            stack.append((level, section))
        else:
            if stack:
                stack[-1][1]["content"].append(el)
            else:
                preamble.append(el)

    return {"preamble": preamble, "sections": root_sections}


def parse_docx(file_bytes: bytes) -> list:
    """Parse DOCX preserving hierarchy and numbering."""
    doc = docx.Document(io.BytesIO(file_bytes))
    elements = []

    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        style = p.style.name if p.style else "Normal"
        level = _detect_heading_level(text, style)
        elements.append({
            "index": len(elements),
            "text": text,
            "type": "heading" if level > 0 else "paragraph",
            "level": level,
            "page": 1
        })

    for t_idx, table in enumerate(doc.tables):
        for r_idx, row in enumerate(table.rows):
            cells = []
            for cell in row.cells:
                ct = cell.text.strip()
                if not cells or cells[-1] != ct:
                    cells.append(ct)
            row_text = " | ".join(c for c in cells if c)
            if row_text:
                elements.append({
                    "index": len(elements),
                    "text": f"[Table {t_idx+1}, Row {r_idx+1}]: {row_text}",
                    "type": "table",
                    "level": 0,
                    "page": 1
                })
    return elements


def parse_pdf(file_bytes: bytes) -> list:
    """Parse PDF preserving hierarchy and page numbers."""
    elements = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for p_idx, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue
            for line in text.split("\n"):
                line_str = line.strip()
                if not line_str:
                    continue
                level = _detect_heading_level(line_str)
                elements.append({
                    "index": len(elements),
                    "text": line_str,
                    "type": "heading" if level > 0 else "paragraph",
                    "level": level,
                    "page": p_idx + 1
                })
    return elements


def extract_document_data(file_bytes: bytes, filename: str) -> dict:
    """Extract text, detect scanned docs, build flat elements + hierarchy."""
    ext = filename.split(".")[-1].lower()
    elements = []
    is_scanned = False

    if ext == "docx":
        elements = parse_docx(file_bytes)
    elif ext == "pdf":
        elements = parse_pdf(file_bytes)
        if not elements:
            is_scanned = True
    else:
        raise ValueError(f"Unsupported file format: {ext}")

    full_text = "\n".join(el["text"] for el in elements)
    if len(full_text.strip()) < 100 and ext == "pdf":
        is_scanned = True

    hierarchy = _build_hierarchy(elements) if not is_scanned else {}

    return {
        "filename": filename,
        "is_scanned": is_scanned,
        "elements": elements,
        "full_text": full_text,
        "hierarchy": hierarchy
    }
