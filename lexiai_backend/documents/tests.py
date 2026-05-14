from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ai_engine.models import DocumentChunk
from ai_engine.tasks import embed_document_chunks

from .models import Document, DocumentIngestionJob
from .services import populate_extracted_text_from_source_file, resolve_ingestion_source

User = get_user_model()


class UploadIngestionPipelineTests(TestCase):
	"""End-to-end checks for API uploads where ``extracted_text`` is initially blank."""

	def setUp(self):
		self.user = User.objects.create_user(email='pipe@example.com', password='password123')

	def test_populate_extracted_text_from_saved_txt_file(self):
		with tempfile.TemporaryDirectory() as media:
			with override_settings(MEDIA_ROOT=media):
				doc = Document(owner=self.user, title='Brief')
				doc.source_file.save(
					'b.txt',
					SimpleUploadedFile('b.txt', b'Alpha beta. Gamma delta.', content_type='text/plain'),
				)
				doc.save()
				self.assertFalse((doc.extracted_text or '').strip())
				self.assertTrue(populate_extracted_text_from_source_file(doc))
				doc.refresh_from_db()
				self.assertIn('Alpha beta', doc.extracted_text)

	@patch('ai_engine.tasks.EmbeddingService.generate_embeddings_batch')
	def test_embed_task_extracts_chunks_and_sets_ready(self, mock_batch):
		mock_batch.side_effect = lambda texts: np.zeros((len(texts), 384), dtype=np.float32)
		with tempfile.TemporaryDirectory() as media:
			with override_settings(MEDIA_ROOT=media):
				doc = Document(owner=self.user, title='Brief')
				doc.source_file.save(
					'c.txt',
					SimpleUploadedFile(
						'c.txt',
						b'Ethiopian tax law applies to residents. This is sentence two.',
						content_type='text/plain',
					),
				)
				doc.save()
				self.assertEqual(doc.status, Document.Status.UPLOADED)
				embed_document_chunks.apply(args=[doc.pk]).get()
				doc.refresh_from_db()
				self.assertEqual(doc.status, Document.Status.READY)
				self.assertGreaterEqual(DocumentChunk.objects.filter(document=doc).count(), 1)
				mock_batch.assert_called_once()

	def test_embed_task_marks_failure_when_no_source_file(self):
		doc = Document.objects.create(owner=self.user, title='Empty', extracted_text='')
		embed_document_chunks.apply(args=[doc.pk]).get()
		doc.refresh_from_db()
		self.assertEqual(doc.status, Document.Status.UPLOADED)
		self.assertTrue((doc.metadata or {}).get('ingestion_failed'))


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
class DocumentIngestionJobApiTests(TransactionTestCase):
	# TransactionTestCase (not APITestCase): ingestion queues work via
	# transaction.on_commit(), which does not run while the test is inside
	# the non-committing atomic block that TestCase/APITestCase uses.

	def setUp(self):
		self.client = APIClient()
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


class AdminDocumentReprocessApiTests(APITestCase):
	def setUp(self):
		self.admin = User.objects.create_user(
			email='reprocess-admin@example.com',
			password='password123',
			is_staff=True,
			is_superuser=True,
		)
		self.owner = User.objects.create_user(email='reprocess-owner@example.com', password='password123')
		self.regular = User.objects.create_user(email='reprocess-regular@example.com', password='password123')
		self.doc = Document.objects.create(
			owner=self.owner,
			title='Reprocess me',
			extracted_text='Some long enough text for chunking. ' * 10,
			status=Document.Status.READY,
		)

	def test_non_admin_cannot_trigger_document_reprocess(self):
		self.client.force_authenticate(user=self.regular)
		response = self.client.post(f'/api/v1/documents/{self.doc.pk}/ingest/', {}, format='json')
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_reprocess_404_when_document_missing(self):
		self.client.force_authenticate(user=self.admin)
		response = self.client.post('/api/v1/documents/999999/ingest/', {}, format='json')
		self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

	def test_reprocess_400_without_extracted_text(self):
		empty_doc = Document.objects.create(
			owner=self.owner,
			title='Empty',
			extracted_text='',
			status=Document.Status.UPLOADED,
		)
		self.client.force_authenticate(user=self.admin)
		response = self.client.post(f'/api/v1/documents/{empty_doc.pk}/ingest/', {}, format='json')
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	def test_admin_triggers_reprocess_queues_task(self):
		from unittest.mock import MagicMock, patch

		self.client.force_authenticate(user=self.admin)
		with patch('ai_engine.tasks.embed_document_chunks.delay') as mock_delay:
			mock_delay.return_value = MagicMock(id='test-celery-task-id')
			response = self.client.post(f'/api/v1/documents/{self.doc.pk}/ingest/', {}, format='json')
			self.assertEqual(response.status_code, status.HTTP_200_OK)
			self.assertEqual(response.data['message'], 'Reprocessing started')
			self.assertEqual(response.data['document_id'], self.doc.pk)
			self.assertEqual(response.data['job_id'], 'test-celery-task-id')
			self.assertEqual(response.data['status'], 'queued')
			mock_delay.assert_called_once_with(self.doc.pk)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class DocumentUploadIngestionIntegrationTests(TransactionTestCase):
	"""Upload via API runs ``transaction.on_commit`` → ``embed_document_chunks`` (eager)."""

	def setUp(self):
		self.client = APIClient()
		self.user = User.objects.create_user(email='upload-ingest@example.com', password='password123')
		self.client.force_authenticate(user=self.user)

	@patch('ai_engine.tasks.EmbeddingService.generate_embeddings_batch')
	def test_multipart_upload_creates_chunks(self, mock_batch):
		mock_batch.side_effect = lambda texts: np.zeros((len(texts), 384), dtype=np.float32)
		with tempfile.TemporaryDirectory() as media:
			with override_settings(MEDIA_ROOT=media):
				uploaded = SimpleUploadedFile(
					'statute.txt',
					b'VAT registration. Income tax obligations. Penalties apply under the law. ' * 4,
					content_type='text/plain',
				)
				response = self.client.post(
					'/api/v1/documents/',
					{'title': 'Tax statute', 'source_file': uploaded},
					format='multipart',
				)
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		doc = Document.objects.get(pk=response.data['id'])
		self.assertEqual(doc.status, Document.Status.READY)
		self.assertGreater(DocumentChunk.objects.filter(document=doc, document_owner=self.user).count(), 0)
		self.assertEqual((doc.metadata or {}).get('ingestion_status'), 'completed')
		mock_batch.assert_called_once()

	def test_debug_chunks_endpoint_self_only(self):
		other = User.objects.create_user(email='other-chunks@example.com', password='password123')
		self.client.force_authenticate(user=other)
		r = self.client.get(f'/api/v1/debug/chunks/{self.user.pk}/')
		self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

	@patch('ai_engine.tasks.EmbeddingService.generate_embeddings_batch')
	def test_debug_chunks_endpoint_returns_count(self, mock_batch):
		mock_batch.side_effect = lambda texts: np.zeros((len(texts), 384), dtype=np.float32)
		with tempfile.TemporaryDirectory() as media:
			with override_settings(MEDIA_ROOT=media):
				uploaded = SimpleUploadedFile(
					'x.txt',
					b'Corporate tax filing deadlines and compliance rules. ' * 4,
					content_type='text/plain',
				)
				self.client.post(
					'/api/v1/documents/',
					{'title': 'T', 'source_file': uploaded},
					format='multipart',
				)
		r = self.client.get(f'/api/v1/debug/chunks/{self.user.pk}/')
		self.assertEqual(r.status_code, status.HTTP_200_OK)
		self.assertEqual(r.data['user_id'], self.user.pk)
		self.assertGreater(r.data['chunk_count'], 0)

	def test_library_stats_endpoint(self):
		Document.objects.create(
			owner=self.user,
			title='No file',
			extracted_text='',
			status=Document.Status.UPLOADED,
		)
		r = self.client.get('/api/v1/documents/library-stats/')
		self.assertEqual(r.status_code, status.HTTP_200_OK)
		self.assertEqual(r.data['owner_id'], self.user.pk)
		self.assertIn('chunk_count_total', r.data)
		self.assertIn('documents', r.data)
		self.assertEqual(r.data['chunk_count_total'], 0)
