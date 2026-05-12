from __future__ import annotations

import json
import logging
import time
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

logger = logging.getLogger(__name__)


def _agent_debug_log(message: str, data: dict, hypothesis_id: str) -> None:
    # region agent log
    payload = {
        'sessionId': 'a2073f',
        'timestamp': int(time.time() * 1000),
        'location': 'documents.services',
        'message': message,
        'data': data,
        'hypothesisId': hypothesis_id,
    }
    line = json.dumps(payload, default=str) + '\n'
    paths: list[Path] = [
        settings.BASE_DIR.parent / 'debug-a2073f.log',
        settings.BASE_DIR / 'debug-a2073f.log',
    ]
    try:
        media_root = settings.MEDIA_ROOT
        media_root.mkdir(parents=True, exist_ok=True)
        paths.append(media_root / 'debug-a2073f.log')
    except OSError:
        pass
    written = False
    for log_path in paths:
        try:
            with open(log_path, 'a', encoding='utf-8') as fh:
                fh.write(line)
            written = True
        except OSError:
            continue
    if not written:
        logger.warning('agent_debug_ndjson_fallback %s', line.strip())
    # endregion


def resolve_ingestion_source(source_dir: str | Path) -> Path:
    """
    Resolve ingestion directory. Relative paths try, in order:
    1) BASE_DIR / name (e.g. tax_doc next to manage.py)
    2) BASE_DIR.parent / name (repo-root sibling; matches Docker ..:/app with tax_doc at /app/tax_doc)
    """
    source_path = Path(source_dir)
    if source_path.is_absolute():
        resolved = source_path.resolve()
        ok = resolved.exists() and resolved.is_dir()
        _agent_debug_log(
            'resolve_ingestion_source absolute',
            {'source_dir': str(source_dir), 'resolved': str(resolved), 'ok': ok},
            'H2',
        )
        if not ok:
            raise CommandError(f'Source directory does not exist: {resolved}')
        return resolved

    candidates = (
        settings.BASE_DIR / source_path,
        settings.BASE_DIR.parent / source_path,
    )
    tried: list[Path] = []
    detail: list[dict] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        tried.append(resolved)
        exists = resolved.exists()
        is_dir = resolved.is_dir() if exists else False
        detail.append({'path': str(resolved), 'exists': exists, 'is_dir': is_dir})
        if exists and is_dir:
            _agent_debug_log(
                'resolve_ingestion_source ok',
                {
                    'source_dir': str(source_dir),
                    'base_dir': str(settings.BASE_DIR),
                    'base_parent': str(settings.BASE_DIR.parent),
                    'chosen': str(resolved),
                    'candidate_detail': detail,
                },
                'H1',
            )
            return resolved
    _agent_debug_log(
        'resolve_ingestion_source failed',
        {
            'source_dir': str(source_dir),
            'base_dir': str(settings.BASE_DIR),
            'base_parent': str(settings.BASE_DIR.parent),
            'candidate_detail': detail,
            'tried': [str(p) for p in tried],
        },
        'H1',
    )
    raise CommandError('Source directory does not exist. Tried: ' + ', '.join(str(p) for p in tried))


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


def _validate_ingestible_file(path: Path) -> Path:
    """Validate a single ingestion target. Returns the resolved absolute path."""
    resolved = path.resolve()
    if not resolved.exists():
        raise CommandError(f'File does not exist: {resolved}')
    if not resolved.is_file():
        raise CommandError(f'Path is not a regular file: {resolved}')
    suffix = resolved.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise CommandError(
            f'Unsupported file type "{suffix}" for {resolved.name}. '
            f'Supported: {", ".join(sorted(SUPPORTED_SUFFIXES))}'
        )
    return resolved


def _ingest_file_into_document(
    path: Path,
    owner,
    *,
    source_path: Path | None = None,
):
    """
    Single-file ingestion primitive shared by directory and single-file ingestion.

    Extracts text, upserts the Document, persists the source file, and queues
    the embedding task on transaction commit. Returns (document, created).
    """
    content = extract_document_text(path)
    relative_source = (
        str(path.relative_to(source_path)) if source_path is not None else path.name
    )
    document, created = Document.objects.update_or_create(
        owner=owner,
        title=build_document_title(path),
        defaults={
            'description': f'Imported from {path.name}',
            'extracted_text': content,
            'analysis_summary': '',
            'status': Document.Status.READY,
            'metadata': {'source_path': relative_source},
        },
    )

    document.source_file.save(path.name, ContentFile(path.read_bytes()), save=True)

    # Trigger asynchronous embedding job AFTER the document is committed.
    # Import inside the function to avoid circular imports in module scope.
    if document.extracted_text and document.extracted_text.strip():
        from django.db import transaction
        from ai_engine.tasks import embed_document_chunks

        doc_pk = document.pk
        transaction.on_commit(lambda pk=doc_pk: embed_document_chunks.delay(pk))

    return document, created


def ingest_documents(
    source_dir: str | Path,
    owner,
    *,
    requested_by=None,
    on_file_progress: ProgressCallback | None = None,
    job=None,
) -> tuple[int, int, int]:
    """
    Ingests all supported documents from a directory.

    Walks ``source_dir`` recursively, processes every file whose suffix is in
    ``SUPPORTED_SUFFIXES`` (.txt, .md, .rtf, .csv, .json, .pdf), upserts a
    ``Document`` per file, copies the source bytes into media storage, and
    queues an asynchronous embedding task per document.

    Returns ``(total_files, created_count, updated_count)``.
    """
    source_path = resolve_ingestion_source(source_dir)
    files = list_ingestible_files(source_path)
    _agent_debug_log(
        'ingest_documents listed files',
        {'source_path': str(source_path), 'file_count': len(files), 'suffixes': sorted(SUPPORTED_SUFFIXES)},
        'H3',
    )

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

        _document, created = _ingest_file_into_document(
            path, owner, source_path=source_path
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

    return len(files), created_count, updated_count


def ingest_single_document(
    file_path: str | Path,
    owner,
    *,
    job=None,
):
    """
    Ingest a single document file.

    - Validates the file exists and has a supported suffix.
    - Extracts text (PDF via pdfplumber/pypdf; plain text otherwise).
    - Creates or updates the corresponding Document.
    - Triggers embedding via ``transaction.on_commit``.

    Returns ``(document, created)``.
    """
    resolved = _validate_ingestible_file(Path(file_path))

    if job is not None:
        job.total_files = 1
        job.processed_files = 0
        job.created_documents = 0
        job.updated_documents = 0
        job.current_file_name = resolved.name
        job.save(update_fields=['total_files', 'processed_files', 'created_documents', 'updated_documents', 'current_file_name', 'updated_at'])

    document, created = _ingest_file_into_document(resolved, owner)

    if job is not None:
        job.processed_files = 1
        job.created_documents = 1 if created else 0
        job.updated_documents = 0 if created else 1
        job.current_file_name = resolved.name
        job.save(update_fields=['processed_files', 'created_documents', 'updated_documents', 'current_file_name', 'updated_at'])

    _agent_debug_log(
        'ingest_single_document done',
        {'path': str(resolved), 'document_id': document.pk, 'created': created},
        'H3',
    )
    return document, created


# --- Backward-compatible alias ---------------------------------------------
# Older code, management commands, or scripts that imported ``ingest_tax_documents``
# continue to work. Prefer ``ingest_documents`` for new code.
ingest_tax_documents = ingest_documents


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