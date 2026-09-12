from io import BytesIO


def clean_text(text: str) -> str:
    if not text:
        return ""

    lines = []

    for line in text.splitlines():
        line = " ".join(line.split())

        if line:
            lines.append(line)

    return "\n".join(lines).strip()


def extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))

    pages = []

    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""

        if text:
            pages.append(text)

    return clean_text("\n".join(pages))


def extract_docx(data: bytes) -> str:
    from docx import Document

    document = Document(BytesIO(data))

    paragraphs = []

    for paragraph in document.paragraphs:
        if paragraph.text:
            paragraphs.append(paragraph.text)

    for table in document.tables:
        for row in table.rows:
            values = []

            for cell in row.cells:
                if cell.text:
                    values.append(cell.text)

            if values:
                paragraphs.append(" | ".join(values))

    return clean_text("\n".join(paragraphs))


def extract_pptx(data: bytes) -> str:
    from pptx import Presentation

    presentation = Presentation(BytesIO(data))

    slides = []

    for slide_number, slide in enumerate(
        presentation.slides,
        start=1,
    ):
        slide_text = [
            f"[الشريحة {slide_number}]"
        ]

        for shape in slide.shapes:
            if hasattr(shape, "text"):
                text = shape.text.strip()

                if text:
                    slide_text.append(text)

        if len(slide_text) > 1:
            slides.append("\n".join(slide_text))

    return clean_text("\n".join(slides))


def extract_plain_text(
    data: bytes,
) -> str:
    encodings = (
        "utf-8",
        "utf-16",
        "cp1256",
        "latin-1",
    )

    for encoding in encodings:
        try:
            return clean_text(
                data.decode(encoding)
            )
        except Exception:
            continue

    return ""


def extract_text_from_bytes(
    data: bytes,
    file_type: str | None,
    file_name: str | None = None,
) -> str:
    file_type = str(
        file_type or ""
    ).lower().strip()

    file_name = str(
        file_name or ""
    ).lower().strip()

    if (
        file_type == "pdf"
        or file_name.endswith(".pdf")
    ):
        return extract_pdf(data)

    if (
        file_type in {
            "docx",
            "word",
            "document",
        }
        or file_name.endswith(".docx")
    ):
        return extract_docx(data)

    if (
        file_type in {
            "pptx",
            "powerpoint",
            "presentation",
        }
        or file_name.endswith(".pptx")
    ):
        return extract_pptx(data)

    if (
        file_type in {
            "txt",
            "text",
            "md",
            "markdown",
            "csv",
        }
        or file_name.endswith(
            (".txt", ".md", ".csv")
        )
    ):
        return extract_plain_text(data)

    return extract_plain_text(data)


async def download_telegram_file(
    bot,
    telegram_file_id: str,
) -> bytes:
    telegram_file = await bot.get_file(
        telegram_file_id
    )

    data = await telegram_file.download_as_bytearray()

    return bytes(data)
