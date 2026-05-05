"""Create small demo files in ../samples/ for each knowledge-base upload type (PDF, images).

Run from repo root: python scripts/generate_kb_samples.py
Requires: Pillow, pymupdf (already in project requirements).
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out = root / "samples"
    out.mkdir(parents=True, exist_ok=True)

    # --- Images (PNG, JPEG, WebP, GIF) — same layout, OCR/vision-friendly text
    w, h = 520, 160
    img = Image.new("RGB", (w, h), (248, 248, 252))
    draw = ImageDraw.Draw(img)
    draw.rectangle([8, 8, w - 8, h - 8], outline=(90, 90, 130), width=3)
    lines = [
        "SAMPLE — Knowledge base image",
        "Fictional: Northbridge Q2 2026 office hours Mon–Fri 9–5 ET.",
        "Support: support@northbridge.example",
    ]
    y = 28
    for line in lines:
        draw.text((28, y), line, fill=(28, 28, 36))
        y += 36

    img.save(out / "sample_kb.png", "PNG")
    rgb = img.convert("RGB")
    rgb.save(out / "sample_kb.jpg", "JPEG", quality=88)
    rgb.save(out / "sample_kb.webp", "WEBP", quality=85)
    img.save(out / "sample_kb.gif", "GIF")

    # --- Minimal one-page PDF with extractable text
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    text = (
        "Sample knowledge base PDF (fictional)\n\n"
        "Policy excerpt: All customer contracts require Legal review before signature. "
        "Standard payment terms are Net 30 unless the order form states otherwise.\n\n"
        "Internal wiki ID: DEMO-POLICY-001"
    )
    page.insert_text((72, 88), text, fontsize=11, fontname="helv", color=(0.1, 0.1, 0.12))
    pdf_path = out / "sample_kb.pdf"
    doc.save(pdf_path)
    doc.close()
    print(f"Wrote samples to {out}")


if __name__ == "__main__":
    main()
