"""Serve the PathFinder Apply browser extension as a downloadable .zip.

Zips the repo's `extension/` folder on the fly (always current) so the web app can
offer a one-click download for the beta / manual-install path, before the extension
is published to the Chrome Web Store.
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


@router.get("/download")
def download_extension():
    if not os.path.isdir(_EXT_DIR):
        return JSONResponse({"detail": "Extension package not found on the server."}, status_code=404)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(_EXT_DIR):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for f in files:
                if f in _SKIP_FILES or f.endswith(".zip"):
                    continue
                fp = os.path.join(root, f)
                arc = os.path.join(_ZIP_ROOT, os.path.relpath(fp, _EXT_DIR))
                z.write(fp, arc)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="pathfinder-apply-extension.zip"'},
    )
