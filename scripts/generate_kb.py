"""
=============================================================
SCRIPT 1 — generate_kb.py
Reads all PDFs from documents/ folder
Extracts text → splits into chunks → writes config/knowledge_base.yaml
=============================================================

Usage:
    python scripts/generate_kb.py

Output:
    config/knowledge_base.yaml
"""

import re
import yaml
import pdfplumber
from pathlib import Path

# ── Paths ───────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent.parent
DOCS_DIR     = BASE_DIR / "documents"
CONFIG_DIR   = BASE_DIR / "config"
OUTPUT_PATH  = CONFIG_DIR / "knowledge_base.yaml"
CONFIG_DIR.mkdir(exist_ok=True)


# =============================================================
# TEXT EXTRACTION
# =============================================================

def extract_text_from_pdf(pdf_path: Path) -> list[dict]:
    """
    Extract text from each page of a PDF.
    Returns list of { page: int, text: str }
    """
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if text and text.strip():
                pages.append({"page": i, "text": text.strip()})
    return pages


# =============================================================
# CHUNKING
# =============================================================

def clean_text(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\(cid:\d+\)', '•', text)   # ← add this line
    return text.strip()


def detect_section(text: str) -> str:
    """
    Try to detect a section heading from the first line of a chunk.
    Returns the heading or 'General' if none found.
    """
    first_line = text.split('\n')[0].strip()
    # Match patterns like "1.2 Root Canal" or "Root Canal Treatment"
    if re.match(r'^[\d]+\.[\d]*\s+\w+', first_line) or len(first_line) < 60:
        return first_line
    return "General"


def split_into_chunks(pages: list[dict], source: str) -> list[dict]:
    """
    Split extracted page text into meaningful chunks.

    Strategy:
    - Join all pages into one text
    - Split on double newlines (paragraph boundaries)
    - Merge short fragments with the previous chunk
    - Skip boilerplate (headers, footers, page numbers)
    - Each chunk gets: id, source, page, section, text
    """
    chunks = []
    chunk_id = 1

    # Patterns to skip (boilerplate)
    skip_patterns = [
        r'^\d+$',
        r'^page \d+',
        r'^dental health knowledge base',
        r'^clinical reference',
        r'^this document is intended',        # ← already there, but not matching
        r'^patients should always consult',   # ← add this
        r'^professional medical advice',      # ← add this
        r'^v\d+\.\d+',
    ]

    for page_data in pages:
        page_num = page_data["page"]
        text     = clean_text(page_data["text"])

        # Split on blank lines
        paragraphs = [p.strip() for p in re.split(r'\n\n+', text) if p.strip()]

        buffer = ""
        for para in paragraphs:
            # Skip boilerplate
            para_lower = para.lower()
            if any(re.match(pat, para_lower) for pat in skip_patterns):
                continue

            # Skip very short fragments (likely headers we'll attach below)
            if len(para) < 40:
                # Could be a section heading — save as buffer prefix
                buffer = para + " — " if buffer == "" else buffer
                continue

            full_para = (buffer + para).strip()
            buffer = ""

            # If chunk is very long, split further at sentence boundaries
            if len(full_para) > 800:
                sentences = re.split(r'(?<=[.!?])\s+', full_para)
                current   = ""
                for sent in sentences:
                    if len(current) + len(sent) < 600:
                        current += " " + sent
                    else:
                        if current.strip():
                            chunks.append({
                                "id":      chunk_id,
                                "source":  source,
                                "page":    page_num,
                                "section": detect_section(current.strip()),
                                "text":    current.strip(),
                            })
                            chunk_id += 1
                        current = sent
                if current.strip():
                    chunks.append({
                        "id":      chunk_id,
                        "source":  source,
                        "page":    page_num,
                        "section": detect_section(current.strip()),
                        "text":    current.strip(),
                    })
                    chunk_id += 1
            else:
                chunks.append({
                    "id":      chunk_id,
                    "source":  source,
                    "page":    page_num,
                    "section": detect_section(full_para),
                    "text":    full_para,
                })
                chunk_id += 1

    return chunks


# =============================================================
# MAIN
# =============================================================

def main():
    pdf_files = sorted(DOCS_DIR.glob("*.pdf"))

    if not pdf_files:
        print(f"✗ No PDF files found in {DOCS_DIR}")
        print("  Place your PDF documents in the documents/ folder and re-run.")
        return

    print(f"Found {len(pdf_files)} PDF file(s) in {DOCS_DIR.name}/\n")

    all_chunks = []

    for pdf_path in pdf_files:
        print(f"  Processing: {pdf_path.name}")
        pages  = extract_text_from_pdf(pdf_path)
        chunks = split_into_chunks(pages, source=pdf_path.name)
        print(f"    → {len(pages)} pages → {len(chunks)} chunks")
        all_chunks.extend(chunks)

    if not all_chunks:
        print("\n✗ No chunks extracted. Check your PDF has selectable text (not scanned images).")
        return

    # ── Build YAML structure ─────────────────────────────────
    kb = {
        "knowledge_base": {
            "domain":      "dental",
            "description": "Auto-generated from source documents in documents/",
            "sources":     [p.name for p in pdf_files],
            "total_chunks": len(all_chunks),
            "chunks":      [c["text"] for c in all_chunks],   # flat list for runner
            "chunks_metadata": all_chunks,                    # full metadata for traceability
        }
    }

    with open(OUTPUT_PATH, "w") as f:
        yaml.dump(kb, f, allow_unicode=True, sort_keys=False, width=120)

    print(f"\n✓ knowledge_base.yaml written → {OUTPUT_PATH}")
    print(f"  Total chunks: {len(all_chunks)}")
    print("\nNext step: python scripts/generate_tests.py")


if __name__ == "__main__":
    main()