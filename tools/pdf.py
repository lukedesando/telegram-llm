import httpx
import pymupdf

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; telegram-llm/1.0)"}


def extract_pdf_text(pdf_bytes: bytes, max_chars: int = 60000) -> str:
    """Extract bounded text from PDF bytes."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        pages_text = []
        total = 0
        for page in doc:
            text = page.get_text()
            pages_text.append(text)
            total += len(text)
            if total >= max_chars:
                break
        return "\n".join(pages_text)[:max_chars]
    finally:
        doc.close()


async def fetch_pdf_bytes(url: str) -> tuple[bytes, str]:
    """Download PDF and return (raw_bytes, filename)."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url, headers=_HEADERS)
        resp.raise_for_status()
    filename = url.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0] or "document.pdf"
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    return resp.content, filename


async def fetch_pdf(url: str, max_chars: int = 60000) -> str:
    pdf_bytes, _ = await fetch_pdf_bytes(url)
    return extract_pdf_text(pdf_bytes, max_chars=max_chars)


async def fetch_pdf_document(url: str, max_chars: int = 60000) -> tuple[bytes, str, str]:
    """Download once and return raw bytes, filename, and extracted bounded text."""
    pdf_bytes, filename = await fetch_pdf_bytes(url)
    return pdf_bytes, filename, extract_pdf_text(pdf_bytes, max_chars=max_chars)


def text_to_pdf(text: str, title: str = "") -> bytes:
    """Generate a simple PDF from plain text."""
    doc = pymupdf.open()
    width, height = 595, 842
    margin = 50
    font_size = 11
    line_height = font_size * 1.4
    usable_w = width - 2 * margin

    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split()
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if pymupdf.get_text_length(test, fontsize=font_size) <= usable_w:
                current = test
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)

    y = margin
    page = doc.new_page(width=width, height=height)

    if title:
        title_size = 14
        page.insert_text((margin, y + title_size), title, fontsize=title_size)
        y += title_size * 2.5

    for line in lines:
        if y + line_height > height - margin:
            page = doc.new_page(width=width, height=height)
            y = margin
        page.insert_text((margin, y + font_size), line, fontsize=font_size)
        y += line_height

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes
