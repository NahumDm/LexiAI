from __future__ import annotations

import tempfile

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from pathlib import Path

from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Document, DocumentIngestionJob
from .services import resolve_ingestion_source

User = get_user_model()


class ResolveIngestionSourceTests(TestCase):
	def test_relative_dir_next_to_django_project_is_found(self):
		with tempfile.TemporaryDirectory() as tmp:
			tmp_path = Path(tmp)
			fake_base = tmp_path / 'lexiai_backend_pkg'
			fake_base.mkdir()
			repo_tax_doc = tmp_path / 'tax_doc'
			repo_tax_doc.mkdir()
			with override_settings(BASE_DIR=fake_base):
				resolved = resolve_ingestion_source('tax_doc')
				self.assertEqual(resolved.resolve(), repo_tax_doc.resolve())

	def test_relative_dir_inside_django_project_takes_priority(self):
		with tempfile.TemporaryDirectory() as tmp:
			tmp_path = Path(tmp)
			fake_base = tmp_path / 'lexiai_backend_pkg'
			fake_base.mkdir()
			inner = fake_base / 'tax_doc'
			inner.mkdir()
			outer = tmp_path / 'tax_doc'
			outer.mkdir()
			with override_settings(BASE_DIR=fake_base):
				resolved = resolve_ingestion_source('tax_doc')
				self.assertEqual(resolved.resolve(), inner.resolve())

	def test_missing_relative_raises_with_tried_paths(self):
		with tempfile.TemporaryDirectory() as tmp:
			fake_base = Path(tmp) / 'lexiai_backend_pkg'
			fake_base.mkdir()
			with override_settings(BASE_DIR=fake_base):
				with self.assertRaises(CommandError) as ctx:
					resolve_ingestion_source('tax_doc')
				self.assertIn('does not exist', str(ctx.exception))
				self.assertIn('Tried:', str(ctx.exception))


class DocumentApiTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(email='user@example.com', password='password123')
		self.other_user = User.objects.create_user(email='other@example.com', password='password123')
		self.client.force_authenticate(user=self.user)

	def test_create_and_list_documents(self):
		response = self.client.post(
			'/api/v1/documents/',
			{
				'title': 'Contract Draft',
				'description': 'Initial draft',
				'status': Document.Status.READY,
			},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(response.data['title'], 'Contract Draft')

		response = self.client.get('/api/v1/documents/')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data['results']), 1)

	def test_document_queryset_is_owner_scoped(self):
		Document.objects.create(owner=self.other_user, title='Other doc')
		response = self.client.get('/api/v1/documents/')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['results'], [])

	def test_upload_file_returns_absolute_url(self):
		uploaded_file = SimpleUploadedFile('brief.txt', b'legal text', content_type='text/plain')
		response = self.client.post(
			'/api/v1/documents/',
			{
				'title': 'Brief',
				'source_file': uploaded_file,
			},
			format='multipart',
		)
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertIn('source_file_url', response.data)


class DocumentIngestCommandTests(APITestCase):
	def setUp(self):
		self.staff_user = User.objects.create_user(email='staff@example.com', password='password123', is_staff=True)

	def test_ingest_command_imports_text_documents(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			source_file = f'{temp_dir}/tax_notice.txt'
			with open(source_file, 'w', encoding='utf-8') as handle:
				handle.write('Imported tax notice content')

			call_command('ingest_tax_docs', source_dir=temp_dir, owner_email=self.staff_user.email)

		document = Document.objects.get(owner=self.staff_user, title='Tax Notice')
		self.assertEqual(document.extracted_text, 'Imported tax notice content')
		self.assertEqual(document.status, Document.Status.READY)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class DocumentIngestionJobApiTests(APITestCase):
	def setUp(self):
		self.admin_user = User.objects.create_user(
			email='admin@example.com',
			password='password123',
			is_staff=True,
			is_superuser=True,
		)
		self.owner_user = User.objects.create_user(email='owner@example.com', password='password123', is_staff=True)
		self.regular_user = User.objects.create_user(email='regular@example.com', password='password123')

	def test_admin_can_trigger_ingestion_and_view_progress(self):
		self.client.force_authenticate(user=self.admin_user)
		with tempfile.TemporaryDirectory() as temp_dir:
			source_file = f'{temp_dir}/tax_notice.txt'
			with open(source_file, 'w', encoding='utf-8') as handle:
				handle.write('API import content')

			response = self.client.post(
				'/api/v1/documents/admin/ingestions/',
				{
					'source_dir': temp_dir,
					'owner_email': self.owner_user.email,
				},
				format='json',
			)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(response.data['status'], DocumentIngestionJob.Status.SUCCEEDED)
		self.assertEqual(response.data['total_files'], 1)
		self.assertEqual(response.data['processed_files'], 1)
		self.assertEqual(response.data['progress_percent'], 100.0)

		job = DocumentIngestionJob.objects.get(pk=response.data['id'])
		self.assertEqual(job.status, DocumentIngestionJob.Status.SUCCEEDED)

		detail_response = self.client.get(f"/api/v1/documents/admin/ingestions/{job.pk}/")
		self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
		self.assertEqual(detail_response.data['processed_files'], 1)

		document = Document.objects.get(owner=self.owner_user, title='Tax Notice')
		self.assertEqual(document.extracted_text, 'API import content')

	def test_non_admin_cannot_trigger_ingestion(self):
		self.client.force_authenticate(user=self.regular_user)
		response = self.client.post(
			'/api/v1/documents/admin/ingestions/',
			{
				'source_dir': 'tax_doc',
				'owner_email': self.owner_user.email,
			},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
