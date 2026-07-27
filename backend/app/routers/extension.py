"""Serve the PathFinder Apply browser extension as a downloadable .zip.

Two always-working delivery paths, both built from the repo's `extension/` source:

1. A **static file** at `/pathfinder-apply-extension.zip` (served by the SPA's
   StaticFiles mount). `refresh_static_zip()` rewrites it from source on app
   startup, so it is always available (no API route needed) AND never stale.
2. This `/api/extension/download` route, which zips on the fly as a fallback.

The static path is what the web app links to (works even if this router or the
`extension/` dir is missing from a given deploy); the route is a secondary path.
"""
from __future__ import annotations

import io
import os
import zipfile

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

router = APIRouter()

_EXT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "extension"))
_SKIP_FILES = {".DS_Store", "Thumbs.db"}
_ZIP_ROOT = "pathfinder-apply"
STATIC_ZIP_NAME = "pathfinder-apply-extension.zip"


def build_extension_zip() -> bytes | None:
    """Zip the `extension/` folder into an in-memory archive rooted at
    `pathfinder-apply/`. Returns the bytes, or None if the source dir is absent."""
    if not os.path.isdir(_EXT_DIR):
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(_EXT_DIR):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for f in sorted(files):
                if f in _SKIP_FILES or f.endswith(".zip"):
                    continue
                fp = os.path.join(root, f)
                arc = os.path.join(_ZIP_ROOT, os.path.relpath(fp, _EXT_DIR))
                z.write(fp, arc)
    return buf.getvalue()


def refresh_static_zip(frontend_dir: str) -> bool:
    """Rebuild the static zip served at `/<STATIC_ZIP_NAME>` from the extension
    source. Best-effort: returns True on success, False if it could not be built
    or written (never raises, so it can't block app startup)."""
    try:
        data = build_extension_zip()
        if data is None or not os.path.isdir(frontend_dir):
            return False
        dest = os.path.join(frontend_dir, STATIC_ZIP_NAME)
        with open(dest, "wb") as fh:
            fh.write(data)
        return True
    except Exception:
        return False


@router.get("/download")
def download_extension():
    data = build_extension_zip()
    if data is None:
        return JSONResponse({"detail": "Extension package not found on the server."}, status_code=404)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{STATIC_ZIP_NAME}"'},
    )
