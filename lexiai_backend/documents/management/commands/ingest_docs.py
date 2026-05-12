from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from documents.services import (
    build_document_title,
    ingest_documents,
    ingest_single_document,
    resolve_ingestion_owner,
)


class Command(BaseCommand):
    help = (
        'Ingest documents into Document records. '
        'Pass --source-dir for batch directory ingestion or --file for a single file. '
        'Supported types: .txt, .md, .rtf, .csv, .json, .pdf.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--source-dir',
            default='tax_doc',
            help='Relative or absolute path to the directory containing documents (used when --file is omitted).',
        )
        parser.add_argument(
            '--file',
            default=None,
            help='Path to a single file to ingest. Mutually exclusive with --source-dir batch mode.',
        )
        parser.add_argument(
            '--owner-email',
            default=None,
            help='Email of the owner to assign imported documents to. Defaults to the first staff user.',
        )

    def handle(self, *args, **options):
        owner = resolve_ingestion_owner(options['owner_email'])
        single_file = options['file']

        if single_file:
            try:
                document, created = ingest_single_document(single_file, owner)
            except CommandError:
                # Re-raise so Django prints a clean error and exits non-zero.
                raise
            verb = 'Created' if created else 'Updated'
            self.stdout.write(
                self.style.SUCCESS(
                    f'{verb} document "{document.title}" (id={document.pk}) from {single_file}.'
                )
            )
            return

        source_dir = options['source_dir']

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
                f'Imported {created_count} new documents, updated {updated_count} existing documents '
                f'({total_files} files processed).'
            )
        )
