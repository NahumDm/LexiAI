from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Document

User = get_user_model()


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
