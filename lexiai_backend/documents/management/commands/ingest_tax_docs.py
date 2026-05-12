from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from documents.services import build_document_title, ingest_documents, resolve_ingestion_owner


class Command(BaseCommand):
    help = (
        'Ingest documents from a directory into Document records. '
        'Generic ingestion command (kept for backward compatibility). '
        'Prefer the newer "ingest_docs" command for new workflows.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--source-dir',
            default='tax_doc',
            help='Relative or absolute path to the directory containing documents to ingest.',
        )
        parser.add_argument(
            '--owner-email',
            default=None,
            help='Email of the owner to assign imported documents to. Defaults to the first staff user.',
        )

    def handle(self, *args, **options):
        source_dir = options['source_dir']
        owner = resolve_ingestion_owner(options['owner_email'])

        def on_file_progress(path: Path, index: int, total: int) -> None:
            self.stdout.write(f'Importing {build_document_title(path)} ({index}/{total})...')

        total_files, created_count, updated_count = ingest_documents(
            source_dir,
            owner,
            on_file_progress=on_file_progress,
        )

        if total_files == 0:
            self.stdout.write(self.style.WARNING(f'No supported files found in {source_dir}'))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f'Imported {created_count} new documents, updated {updated_count} existing documents.'
            )
        )
