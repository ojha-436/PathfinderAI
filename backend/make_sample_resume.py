"""Generate a real, text-based sample resume PDF (Asha) for the golden-path demo.

Produces app/data/sample_resume_asha.pdf — a minimal but valid PDF whose text is
selectable/extractable by pypdf (so it exercises the real R1 upload path, not a mock).

Run:  python make_sample_resume.py
"""
from __future__ import annotations

import os

LINES = [
    "Asha Kulkarni",
    "Data Entry Operator  |  Pune, Maharashtra",
    "asha.kulkarni@example.com  |  +91 98765 43210",
    "",
    "PROFILE",
    "Detail-oriented Data Entry Operator with 8 years of experience in",
    "high-volume data entry, record keeping and document filing.",
    "",
    "SKILLS",
    "Data Entry, Typing, Microsoft Excel, Basic MS Office, Filing,",
    "Cash Handling, Attention to Detail, Customer Service,",
    "Business Communication, Time Management",
    "",
    "EXPERIENCE",
    "Senior Data Entry Operator, Acme Logistics (2018 - 2026)",
    "- Entered and validated 500+ records daily in Excel and internal systems",
    "- Maintained physical and digital filing with 99.8% accuracy",
    "- Handled customer telephone queries and the billing counter",
    "",
    "EDUCATION",
    "B.Com, Savitribai Phule Pune University (2016)",
]


def _escape(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_pdf() -> bytes:
    # Content stream: one text block, 12pt Helvetica, 16pt leading.
    body = ["BT", "/F1 12 Tf", "16 TL", "50 760 Td"]
    for ln in LINES:
        body.append(f"({_escape(ln)}) Tj")
        body.append("T*")
    body.append("ET")
    content = "\n".join(body).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_pos = len(out)
    n = len(objects) + 1
    out += f"xref\n0 {n}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += b"trailer\n"
    out += f"<< /Size {n} /Root 1 0 R >>\n".encode()
    out += b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF"
    return bytes(out)


def main() -> None:
    data_dir = os.path.join(os.path.dirname(__file__), "app", "data")
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "sample_resume_asha.pdf")
    with open(path, "wb") as f:
        f.write(build_pdf())
    print(f"wrote {path} ({os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
