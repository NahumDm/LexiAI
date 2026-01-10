# pyright: reportGeneralTypeIssues=false

import os
import json
from typing import cast, Sequence

import ocrmypdf
from pypdf import PdfReader, PageObject
from tqdm import tqdm

RAW_DIR = "data/raw"
OCR_DIR = "data/ocr"
TEXT_DIR = "data/text"

os.makedirs(OCR_DIR, exist_ok=True)
os.makedirs(TEXT_DIR, exist_ok=True)


def is_scanned_pdf(path):
    """Checks if PDF is scanned by testing whether the first page has extractable text."""
    try:
        reader = PdfReader(path)
        page = cast(PageObject, reader.pages[0])
        text = page.extract_text()  # type: ignore[operator]
        return text is None or len(text.strip()) == 0
    except Exception:
        return True


def run_ocr(input_path, output_path):
    """Runs OCR using ocrmypdf."""
    try:
        ocrmypdf.ocr(
            input_path,
            output_path,
            deskew=True,
            rotate_pages=True,
            clean=True,
            clean_final=True,
            skip_text=True,
        )
        return True
    except Exception as e:
        print(f"❌ OCR failed for {input_path}: {e}")
        return False


def extract_text(input_pdf: str, output_txt: str) -> None:
    reader = PdfReader(input_pdf)
    pages = cast(Sequence[PageObject], reader.pages)

    text_parts = []
    for page in pages:
        text_parts.append(page.extract_text() or "")

    with open(output_txt, "w", encoding="utf-8") as fh:
        fh.write("\n".join(text_parts))


def save_metadata(pdf_path, output_text_path):
    metadata = {
        "file_name": os.path.basename(pdf_path),
        "text_output": output_text_path,
        "size_kb": round(os.path.getsize(pdf_path) / 1024, 2),
    }

    json_path = output_text_path.replace(".txt", ".json")
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(metadata, jf, indent=4)


def ingest_all():
    pdf_files = [f for f in os.listdir(RAW_DIR) if f.lower().endswith(".pdf")]

    print(f"📌 Ingesting {len(pdf_files)} PDFs...\n")

    for file in tqdm(pdf_files):
        input_path = os.path.join(RAW_DIR, file)
        ocr_output_pdf = os.path.join(OCR_DIR, file)
        text_output = os.path.join(TEXT_DIR, file.replace(".pdf", ".txt"))

        print(f"\n➡ Processing: {file}")

        scanned = is_scanned_pdf(input_path)

        if scanned:
            print("🟡 Scanned detected → Running OCR...")
            success = run_ocr(input_path, ocr_output_pdf)
            if not success:
                print("❌ Skipping due to OCR error.")
                continue
            pdf_for_extraction = ocr_output_pdf
        else:
            print("🟢 Text‑based PDF → No OCR needed.")
            pdf_for_extraction = input_path

        print("📄 Extracting text...")
        extract_text(pdf_for_extraction, text_output)

        save_metadata(input_path, text_output)

    print("\n🎉 Ingestion completed successfully!")


if __name__ == "__main__":
    ingest_all()
