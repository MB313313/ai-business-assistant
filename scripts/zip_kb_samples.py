"""Build frontend-react/public/sample.zip with a root folder `sample/` containing all KB demo files.

Run from repo root: python scripts/zip_kb_samples.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
OUT_ZIP = ROOT / "frontend-react" / "public" / "sample.zip"

FILES = [
    "apex_digital_hr_faq.txt",
    "sample_kb.pdf",
    "sample_kb.png",
    "sample_kb.jpg",
    "sample_kb.webp",
    "sample_kb.gif",
]


def main() -> None:
    OUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in FILES:
            path = SAMPLES / name
            if not path.is_file():
                raise SystemExit(f"Missing sample file: {path} (run generate_kb_samples or add files)")
            zf.write(path, arcname=f"sample/{name}")
    print(f"Wrote {OUT_ZIP} ({len(FILES)} files under sample/)")


if __name__ == "__main__":
    main()
