from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from documents.models import Document

from .models import Conversation, ConversationMessage

User = get_user_model()


class ConversationApiTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(email='user@example.com', password='password123')
		self.other_user = User.objects.create_user(email='other@example.com', password='password123')
		self.document = Document.objects.create(owner=self.user, title='Case File')
		self.client.force_authenticate(user=self.user)

	def test_create_and_list_conversations(self):
		response = self.client.post(
			'/api/v1/conversations/',
			{
				'title': 'Client Intake',
				'document': self.document.id,
			},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(response.data['title'], 'Client Intake')

		response = self.client.get('/api/v1/conversations/')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data['results']), 1)

	def test_cannot_attach_someone_elses_document(self):
		other_document = Document.objects.create(owner=self.other_user, title='Other Case File')
		response = self.client.post(
			'/api/v1/conversations/',
			{
				'title': 'Invalid Attach',
				'document': other_document.id,
			},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	def test_cannot_access_other_users_conversation(self):
		conversation = Conversation.objects.create(owner=self.other_user, title='Private')
		response = self.client.get(f'/api/v1/conversations/{conversation.id}/')
		self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

	def test_conversation_queryset_is_owner_scoped(self):
		Conversation.objects.create(owner=self.other_user, title='Other convo')
		response = self.client.get('/api/v1/conversations/')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['results'], [])

	def test_create_message_for_conversation(self):
		conversation = Conversation.objects.create(owner=self.user, title='Advice')
		response = self.client.post(
			f'/api/v1/conversations/{conversation.id}/messages/',
			{
				'content': 'What should I review first?',
			},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(response.data['sender'], ConversationMessage.Sender.USER)
		conversation.refresh_from_db()
		self.assertIsNotNone(conversation.last_message_at)

		response = self.client.get(f'/api/v1/conversations/{conversation.id}/messages/')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data['results']), 1)

	def test_rejects_non_user_sender_through_public_endpoint(self):
		conversation = Conversation.objects.create(owner=self.user, title='Advice')
		response = self.client.post(
			f'/api/v1/conversations/{conversation.id}/messages/',
			{
				'sender': ConversationMessage.Sender.ASSISTANT,
				'content': 'Assistant message should not be client-created',
			},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	def test_owner_can_update_own_conversation(self):
		conversation = Conversation.objects.create(owner=self.user, title='Advice')
		response = self.client.patch(
			f'/api/v1/conversations/{conversation.id}/',
			{
				'title': 'Updated Advice',
				'status': Conversation.Status.CLOSED,
			},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		conversation.refresh_from_db()
		self.assertEqual(conversation.title, 'Updated Advice')
		self.assertEqual(conversation.status, Conversation.Status.CLOSED)

	def test_cannot_post_message_to_other_users_conversation(self):
		conversation = Conversation.objects.create(owner=self.other_user, title='Advice')
		response = self.client.post(
			f'/api/v1/conversations/{conversation.id}/messages/',
			{
				'sender': ConversationMessage.Sender.USER,
				'content': 'Unauthorized access attempt',
			},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
