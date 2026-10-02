"""Generate test PDFs and images with PyMuPDF/Pillow (no binaries in the repo)."""

from __future__ import annotations

import io

import pymupdf
from PIL import Image, ImageDraw

LOREM = (
    "The quick brown fox jumps over the lazy dog. "
    "Pack my box with five dozen liquor jugs."
)


def text_pdf(path: str, pages: int = 3, width: float = 595, height: float = 842) -> str:
    """Pages containing 'Page N' headings and a couple of text lines."""
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=width, height=height)
        page.insert_text((72, 72), f"Page {i + 1}", fontsize=24, fontname="helv")
        page.insert_text((72, 120), LOREM[:44], fontsize=12, fontname="helv")
        page.insert_text((72, 140), LOREM[45:], fontsize=12, fontname="tiro")
        page.insert_text((72, 180), f"Unique marker {i + 1:03d}", fontsize=11, fontname="cour", color=(0, 0, 1))
    doc.set_metadata({"title": "Sample", "author": "Tester"})
    doc.save(path, deflate=True)
    doc.close()
    return path


def outline_pdf(path: str) -> str:
    """Five pages with a nested outline."""
    text_pdf(path, pages=5)
    doc = pymupdf.open(path)
    doc.set_toc([[1, "Chapter 1", 1], [2, "Section 1.1", 2], [2, "Section 1.2", 3], [1, "Chapter 2", 4]])
    doc.saveIncr()
    doc.close()
    return path


def png_bytes(width: int = 200, height: int = 120, color=(220, 40, 40), alpha: bool = False) -> bytes:
    mode = "RGBA" if alpha else "RGB"
    fill = color + (255,) if alpha else color
    img = Image.new(mode, (width, height), fill)
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, width // 2, height // 2], fill=(20, 20, 200) + ((255,) if alpha else ()))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def jpeg_bytes(width: int = 1200, height: int = 900, quality: int = 95) -> bytes:
    """A noisy photo-like JPEG (compresses poorly, good for compression tests)."""
    img = Image.effect_noise((width, height), 60).convert("RGB")
    draw = ImageDraw.Draw(img)
    for i in range(0, width, 40):
        draw.line([(i, 0), (width - i, height)], fill=(i % 255, 120, 200), width=6)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def image_file(path: str, fmt: str = "PNG", size=(300, 200)) -> str:
    img = Image.new("RGB", size, (30, 140, 60))
    ImageDraw.Draw(img).ellipse([20, 20, size[0] - 20, size[1] - 20], fill=(250, 250, 0))
    img.save(path, fmt)
    return path


def image_pdf(path: str, pages: int = 2) -> str:
    """Pages with a large photo-like JPEG and a small PNG each."""
    doc = pymupdf.open()
    jpg = jpeg_bytes()
    png = png_bytes()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 60), f"Images page {i + 1}", fontsize=14)
        page.insert_image(pymupdf.Rect(72, 80, 372, 305), stream=jpg)
        page.insert_image(pymupdf.Rect(400, 80, 500, 140), stream=png)
    doc.save(path, deflate=True)
    doc.close()
    return path


def form_pdf(path: str) -> str:
    """One page with text, checkbox, radio group, combo box and list box fields."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Form test", fontsize=16)

    def add(kind, name, rect, **attrs):
        w = pymupdf.Widget()
        w.field_type = kind
        w.field_name = name
        w.rect = pymupdf.Rect(rect)
        for key, value in attrs.items():
            setattr(w, key, value)
        page.add_widget(w)

    add(pymupdf.PDF_WIDGET_TYPE_TEXT, "name", (72, 80, 300, 100), field_value="")
    add(pymupdf.PDF_WIDGET_TYPE_CHECKBOX, "agree", (72, 110, 90, 128), field_value=False)
    add(pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON, "size", (72, 140, 90, 158), field_value=False)
    add(pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON, "size", (100, 140, 118, 158), field_value=False)
    add(
        pymupdf.PDF_WIDGET_TYPE_COMBOBOX,
        "color",
        (72, 170, 200, 190),
        choice_values=["Red", "Green", "Blue"],
        field_value="Red",
    )
    add(
        pymupdf.PDF_WIDGET_TYPE_LISTBOX,
        "fruit",
        (72, 200, 200, 260),
        choice_values=["Apple", "Banana", "Cherry"],
        field_value="Apple",
    )
    doc.save(path, deflate=True)
    doc.close()
    return path


def annotated_pdf(path: str) -> str:
    """Two text pages with a few annotations on the first page."""
    text_pdf(path, pages=2)
    doc = pymupdf.open(path)
    page = doc[0]
    page.add_highlight_annot(page.search_for("quick brown")[0])
    rect = page.add_rect_annot((300, 300, 400, 380))
    rect.set_colors(stroke=(1, 0, 0))
    rect.update()
    page.add_text_annot((450, 450), "A sticky note")
    doc.saveIncr()
    doc.close()
    return path


def encrypted_pdf(path: str, user: str = "user", owner: str = "owner", permissions: int | None = None) -> str:
    """A text PDF protected with AES-256."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Secret content", fontsize=14)
    perms = permissions if permissions is not None else int(pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_COPY)
    doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=user, owner_pw=owner, permissions=perms)
    doc.close()
    return path


def scanned_pdf(path: str, text: str = "Scanned invoice number 12345") -> str:
    """A page that only contains an image of text (needs OCR to be searchable)."""
    src = pymupdf.open()
    page = src.new_page(width=612, height=792)
    page.insert_text((72, 120), text, fontsize=24)
    pix = page.get_pixmap(dpi=200)
    doc = pymupdf.open()
    out = doc.new_page(width=612, height=792)
    out.insert_image(out.rect, stream=pix.tobytes("png"))
    doc.save(path, deflate=True)
    doc.close()
    src.close()
    return path
