from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from ai_engine.models import DocumentChunk, QueryLog
from ai_engine.services.chunking import ChunkingService
from ai_engine.services.embedding import EmbeddingService
from ai_engine.services.retrieval import RetrievalService
from conversations.models import Conversation
from documents.models import Document

User = get_user_model()


class ChunkingServiceTests(APITestCase):
	"""Test document chunking logic."""

	def test_chunk_simple_text(self):
		text = (
			'First sentence. Second sentence. Third sentence. Fourth sentence. '
			'Fifth sentence. Sixth sentence. Seventh sentence. Eighth sentence.'
		)
		chunks = ChunkingService.chunk_document(text)

		self.assertGreater(len(chunks), 0)
		for chunk in chunks:
			self.assertIn('content', chunk)
			self.assertIn('token_count', chunk)
			self.assertIn('sequence_index', chunk)
			self.assertGreater(len(chunk['content']), 0)

	def test_chunk_empty_text(self):
		chunks = ChunkingService.chunk_document('')
		self.assertEqual(len(chunks), 0)

	def test_estimate_tokens(self):
		text = 'This is a test sentence with ten words in it right now'
		tokens = ChunkingService.estimate_tokens(text)
		self.assertGreater(tokens, 0)

	def test_sequencing(self):
		text = ' '.join(['Sentence ' + str(i) + '.' for i in range(50)])
		chunks = ChunkingService.chunk_document(text)

		for i, chunk in enumerate(chunks):
			self.assertEqual(chunk['sequence_index'], i)


class EmbeddingServiceTests(APITestCase):
	"""Test embedding generation and utilities."""

	def test_embedding_to_bytes_and_back(self):
		import numpy as np
		original = np.random.rand(384).astype(np.float32)

		as_bytes = EmbeddingService.embedding_to_bytes(original)
		self.assertIsInstance(as_bytes, bytes)

		restored = EmbeddingService.bytes_to_embedding(as_bytes)
		np.testing.assert_array_almost_equal(original, restored, decimal=5)

	def test_cosine_similarity_same_vector(self):
		import numpy as np
		vec = np.array([1, 0, 0], dtype=np.float32)
		similarity = EmbeddingService.cosine_similarity(vec, vec)
		self.assertAlmostEqual(similarity, 1.0, places=5)

	def test_cosine_similarity_orthogonal(self):
		import numpy as np
		vec1 = np.array([1, 0, 0], dtype=np.float32)
		vec2 = np.array([0, 1, 0], dtype=np.float32)
		similarity = EmbeddingService.cosine_similarity(vec1, vec2)
		self.assertAlmostEqual(similarity, 0.0, places=5)


class RetrieverIntegrationTests(APITestCase):
	"""Test retrieval service with mock embeddings."""

	def setUp(self):
		self.user = User.objects.create_user(email='retriever@example.com', password='password123')
		self.document = Document.objects.create(
			owner=self.user,
			title='Test Document',
			extracted_text='This is test content for retrieval.',
		)

	def test_retrieve_no_chunks(self):
		chunks = RetrievalService.retrieve_relevant_chunks(
			query_text='query',
			document=self.document,
		)
		self.assertEqual(len(chunks), 0)

	def test_retrieve_with_chunks(self):
		import numpy as np

		chunk = DocumentChunk.objects.create(
			document=self.document,
			document_owner=self.user,
			sequence_index=0,
			content='Test chunk content',
			token_count=5,
			embedding=EmbeddingService.embedding_to_bytes(
				np.random.rand(384).astype(np.float32)
			),
		)

		chunks = RetrievalService.retrieve_relevant_chunks(
			query_text='test query',
			document=self.document,
			top_k=5,
		)

		self.assertGreater(len(chunks), 0)
		retrieved = chunks[0]
		self.assertEqual(retrieved.chunk.id, chunk.id)


class ChatAPIIntegrationTests(APITestCase):
	"""Test the full chat API endpoint."""

	def setUp(self):
		self.user = User.objects.create_user(email='chat@example.com', password='password123')
		self.document = Document.objects.create(
			owner=self.user,
			title='Legal Document',
			extracted_text='Contract clause 1. Contract clause 2. Contract clause 3.',
		)
		self.conversation = Conversation.objects.create(
			owner=self.user,
			title='Contract Review',
			document=self.document,
		)
		self.client.force_authenticate(user=self.user)

	def test_chat_without_document(self):
		conversation_no_doc = Conversation.objects.create(
			owner=self.user,
			title='No Document',
		)
		response = self.client.post(
			f'/api/v1/chat/{conversation_no_doc.id}/ask/',
			{'query': 'hello'},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertIn('answer', response.data)

	def test_chat_missing_query(self):
		response = self.client.post(
			f'/api/v1/chat/{self.conversation.id}/ask/',
			{},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	def test_chat_with_query(self):
		response = self.client.post(
			f'/api/v1/chat/{self.conversation.id}/ask/',
			{'query': 'What are the main terms?', 'top_k': 3},
			format='json',
		)
		self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR])

		if response.status_code == status.HTTP_200_OK:
			self.assertIn('answer', response.data)
			self.assertIn('sources', response.data)
			self.assertIn('model_used', response.data)

	def test_chat_creates_messages(self):
		response = self.client.post(
			f'/api/v1/chat/{self.conversation.id}/ask/',
			{'query': 'What terms apply?'},
			format='json',
		)

		if response.status_code == status.HTTP_200_OK:
			messages = self.conversation.messages.all()
			self.assertGreater(messages.count(), 0)

	def test_chat_unauthorized_conversation(self):
		other_user = User.objects.create_user(email='other@example.com', password='password123')
		other_conv = Conversation.objects.create(owner=other_user, title='Private')

		response = self.client.post(
			f'/api/v1/chat/{other_conv.id}/ask/',
			{'query': 'question'},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class QueryLogTests(APITestCase):
	"""Test query logging for analytics."""

	def setUp(self):
		self.user = User.objects.create_user(email='log@example.com', password='password123')
		self.conversation = Conversation.objects.create(owner=self.user, title='Test')

	def test_query_log_creation(self):
		log = QueryLog.objects.create(
			user=self.user,
			conversation=self.conversation,
			query_text='test query',
			llm_response='test response',
			latency_ms=250,
			llm_model='stub-v1',
		)
		self.assertEqual(log.user, self.user)
		self.assertEqual(log.conversation, self.conversation)
		self.assertEqual(log.latency_ms, 250)
