from __future__ import annotations

from pathlib import Path
from typing import Callable

import pdfplumber
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import CommandError
from pypdf import PdfReader

from .models import Document

SUPPORTED_SUFFIXES = {'.txt', '.md', '.rtf', '.csv', '.json', '.pdf'}
ProgressCallback = Callable[[Path, int, int], None]


def resolve_ingestion_source(source_dir: str | Path) -> Path:
    source_path = Path(source_dir)
    if not source_path.is_absolute():
        source_path = settings.BASE_DIR / source_path
    if not source_path.exists() or not source_path.is_dir():
        raise CommandError(f'Source directory does not exist: {source_path}')
    return source_path


def resolve_ingestion_owner(owner_email: str | None = None):
    User = get_user_model()
    if owner_email:
        try:
            return User.objects.get(email=owner_email)
        except User.DoesNotExist as exc:
            raise CommandError(f'Owner not found: {owner_email}') from exc

    owner = User.objects.filter(is_staff=True).order_by('id').first()
    if owner is None:
        raise CommandError('No staff user exists. Create one or pass --owner-email.')
    return owner


def list_ingestible_files(source_dir: Path) -> list[Path]:
    return [
        path for path in sorted(source_dir.rglob('*'))
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    ]


def ingest_tax_documents(
    source_dir: str | Path,
    owner,
    *,
    requested_by=None,
    on_file_progress: ProgressCallback | None = None,
    job=None,
) -> tuple[int, int, int]:
    source_path = resolve_ingestion_source(source_dir)
    files = list_ingestible_files(source_path)

    created_count = 0
    updated_count = 0
    if job is not None:
        job.total_files = len(files)
        job.processed_files = 0
        job.created_documents = 0
        job.updated_documents = 0
        job.current_file_name = ''
        if requested_by is not None:
            job.requested_by = requested_by
        job.save(update_fields=['total_files', 'processed_files', 'created_documents', 'updated_documents', 'current_file_name', 'requested_by', 'updated_at'])

    for index, path in enumerate(files, start=1):
        if on_file_progress is not None:
            on_file_progress(path, index, len(files))

        content = extract_document_text(path)
        document, created = Document.objects.update_or_create(
            owner=owner,
            title=build_document_title(path),
            defaults={
                'description': f'Imported from {path.name}',
                'extracted_text': content,
                'analysis_summary': '',
                'status': Document.Status.READY,
                'metadata': {'source_path': str(path.relative_to(source_path))},
            },
        )

        if created:
            created_count += 1
        else:
            updated_count += 1

        if job is not None:
            job.processed_files = index
            job.created_documents = created_count
            job.updated_documents = updated_count
            job.current_file_name = path.name
            job.save(update_fields=['processed_files', 'created_documents', 'updated_documents', 'current_file_name', 'updated_at'])

        document.source_file.save(path.name, ContentFile(path.read_bytes()), save=True)

    return len(files), created_count, updated_count


def build_document_title(path: Path) -> str:
    return path.stem.replace('_', ' ').replace('-', ' ').title()


def extract_document_text(path: Path) -> str:
    if path.suffix.lower() == '.pdf':
        return extract_pdf_text(path)
    return path.read_text(encoding='utf-8', errors='ignore')


def extract_pdf_text(path: Path) -> str:
    try:
        return extract_pdf_text_with_pdfplumber(path)
    except Exception:
        return extract_pdf_text_with_pypdf(path)


def extract_pdf_text_with_pdfplumber(path: Path) -> str:
    extracted_pages = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ''
            if page_text.strip():
                extracted_pages.append(page_text.strip())
    return '\n\n'.join(extracted_pages).strip()


def extract_pdf_text_with_pypdf(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
    except Exception:
        return ''

    extracted_pages = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ''
        except Exception:
            page_text = ''
        if page_text.strip():
            extracted_pages.append(page_text.strip())
    return '\n\n'.join(extracted_pages).strip()