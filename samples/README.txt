Knowledge base demo files
=========================

These files match the types you can upload in the sidebar (PDF, TXT, PNG, JPEG, WebP, GIF).

The app offers one download: sample.zip (built into frontend-react/public/). It contains a folder named "sample" with all of these files.

Rebuild the zip after changing files here:

  python scripts/zip_kb_samples.py

Regenerate PDF/images from an updated PNG:

  python scripts/generate_kb_samples.py

(Requires Pillow and PyMuPDF — same as backend requirements.)
