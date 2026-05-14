from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from ai_engine.models import DocumentChunk, QueryLog
from ai_engine.query_classification import (
	ASK_GREETING_RESPONSE,
	ASK_OUT_OF_SCOPE_RESPONSE,
)
from ai_engine.services.qa import generate_answer
from ai_engine.strict_grounding import STRICT_NO_RETRIEVAL_ANSWER
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
		from django.test import override_settings

		with override_settings(RAG_MIN_SIMILARITY=0.0):
			# Align stored chunk vector with the query embedding so cosine ≥ floor
			# (random vs query often scores < 0 and is filtered even when floor is 0).
			query_text = 'test query'
			query_emb = EmbeddingService.generate_embedding(query_text)
			chunk = DocumentChunk.objects.create(
				document=self.document,
				document_owner=self.user,
				sequence_index=0,
				content='Test chunk content',
				token_count=5,
				embedding=EmbeddingService.embedding_to_bytes(query_emb),
			)

			chunks = RetrievalService.retrieve_relevant_chunks(
				query_text=query_text,
				document=self.document,
				top_k=5,
			)

			self.assertGreater(len(chunks), 0)
			retrieved = chunks[0]
			self.assertEqual(retrieved.chunk.id, chunk.id)

	def test_retrieve_includes_staff_global_kb_for_regular_user(self):
		from django.test import override_settings

		staff = User.objects.create_user(email='staff-kb@example.com', password='password123', is_staff=True)
		admin_doc = Document.objects.create(
			owner=staff,
			title='Tax law KB',
			extracted_text='VAT and corporate tax reference.',
		)
		query_text = 'vat retrieval probe unique phrase'
		query_emb = EmbeddingService.generate_embedding(query_text)
		DocumentChunk.objects.create(
			document=admin_doc,
			document_owner=staff,
			sequence_index=0,
			content='VAT registration and compliance rules for businesses.',
			token_count=10,
			embedding=EmbeddingService.embedding_to_bytes(query_emb),
		)
		with override_settings(RAG_MIN_SIMILARITY=0.0):
			hits = RetrievalService.retrieve_relevant_chunks(
				query_text=query_text,
				document=None,
				user=self.user,
				top_k=5,
			)
		self.assertGreater(len(hits), 0)
		self.assertEqual(hits[0].source, 'admin')

	def test_retrieve_document_denied_for_other_user_private_doc(self):
		from django.test import override_settings

		other = User.objects.create_user(email='other-private@example.com', password='password123')
		other_doc = Document.objects.create(owner=other, title='Private', extracted_text='Secret clause.')
		query_text = 'secret clause retrieval'
		query_emb = EmbeddingService.generate_embedding(query_text)
		DocumentChunk.objects.create(
			document=other_doc,
			document_owner=other,
			sequence_index=0,
			content='Secret clause alpha bravo charlie.',
			token_count=6,
			embedding=EmbeddingService.embedding_to_bytes(query_emb),
		)
		with override_settings(RAG_MIN_SIMILARITY=0.0):
			hits = RetrievalService.retrieve_relevant_chunks(
				query_text=query_text,
				document=other_doc,
				user=None,
				top_k=5,
				accessing_user=self.user,
			)
		self.assertEqual(len(hits), 0)


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
		self.assertEqual(response.data['answer'], ASK_GREETING_RESPONSE)

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


_COMPLIANT_TWO_CHUNK_ANSWER = (
	'Answer:\n'
	'Combined.\n\n'
	'Legal Basis:\n'
	'- [1] First passage.\n'
	'- [2] Second passage.\n\n'
	'Explanation:\n'
	'Both passages support the answer.\n\n'
	'Sources:\n'
	'[1] A\n'
	'[2] A\n'
)

_COMPLIANT_ONE_CHUNK_ANSWER = (
	'Answer:\n'
	'Under [1], the rule applies.\n\n'
	'Legal Basis:\n'
	'- [1] Federal Income Tax Proclamation\n\n'
	'Explanation:\n'
	'Penalties follow from the cited passage.\n\n'
	'Sources:\n'
	'[1] Federal Income Tax Proclamation\n'
)


class AskGenerateAnswerRoutingTests(APITestCase):
	"""Deterministic /ask routing when retrieval is empty or strict RAG when chunks exist."""

	def setUp(self):
		self.user = User.objects.create_user(email='askroute@example.com', password='password123')

	@patch('ai_engine.services.qa.semantic_search')
	def test_greeting_no_retrieval(self, mock_search):
		out = generate_answer('hi', user=self.user, save_log=False)
		self.assertEqual(out['answer'], ASK_GREETING_RESPONSE)
		self.assertEqual(out['confidence'], 1.0)
		self.assertEqual(out['confidence_percent'], 100.0)
		self.assertEqual(out['sources'], [])
		mock_search.assert_not_called()

	@patch('ai_engine.services.qa.semantic_search')
	def test_out_of_scope_no_retrieval(self, mock_search):
		out = generate_answer('Who won the football world cup?', user=self.user, save_log=False)
		self.assertEqual(out['answer'], ASK_OUT_OF_SCOPE_RESPONSE)
		self.assertEqual(out['confidence'], 1.0)
		self.assertEqual(out['sources'], [])
		mock_search.assert_not_called()

	@patch('ai_engine.services.qa.semantic_search')
	def test_legal_no_chunks_strict_refusal(self, mock_search):
		mock_search.return_value = ([], 0.0)
		out = generate_answer('What are the penalties for tax evasion?', user=self.user, save_log=False)
		self.assertEqual(out['answer'], STRICT_NO_RETRIEVAL_ANSWER)
		self.assertEqual(out['confidence'], 0.0)
		self.assertEqual(out['sources'], [])
		mock_search.assert_called_once()

	@patch('ai_engine.services.qa.semantic_search')
	def test_unknown_no_chunks_strict_refusal(self, mock_search):
		mock_search.return_value = ([], 0.0)
		out = generate_answer('Who won the world cup?', user=self.user, save_log=False)
		self.assertEqual(out['answer'], STRICT_NO_RETRIEVAL_ANSWER)
		self.assertEqual(out['confidence'], 0.0)
		mock_search.assert_called_once()

	@patch('ai_engine.services.qa.generate_completion', return_value=_COMPLIANT_TWO_CHUNK_ANSWER)
	@patch('ai_engine.services.qa.semantic_search')
	def test_strict_rag_confidence_blended(self, mock_search, _mock_llm):
		c1 = MagicMock()
		c1.id = 1
		c1.document_id = 1
		c1.document = MagicMock()
		c1.document.title = 'A'
		c1.content = 'First passage.'
		c1.relevance_score = 0.5
		c2 = MagicMock()
		c2.id = 2
		c2.document_id = 1
		c2.document = MagicMock()
		c2.document.title = 'A'
		c2.content = 'Second passage.'
		c2.relevance_score = 0.9
		mock_search.return_value = ([c1, c2], 0.9)
		out = generate_answer('What does the tax law say?', user=self.user, save_log=False)
		self.assertAlmostEqual(out['confidence'], 0.892, places=5)
		self.assertEqual(out['confidence_percent'], 89.2)
		self.assertAlmostEqual(out['retrieval_confidence'], 0.7, places=5)

	@patch('ai_engine.services.qa.generate_completion', return_value=_COMPLIANT_ONE_CHUNK_ANSWER)
	@patch('ai_engine.services.qa.semantic_search')
	def test_strict_rag_uses_chunk_similarity_confidence(self, mock_search, _mock_llm):
		ch = MagicMock()
		ch.id = 42
		ch.document_id = 7
		ch.document = MagicMock()
		ch.document.title = 'Federal Income Tax Proclamation'
		ch.content = 'A taxpayer who conceals income shall be subject to penalties as described herein.'
		ch.relevance_score = 0.78
		mock_search.return_value = ([ch], 0.78)
		out = generate_answer(
			'What penalties apply for tax evasion under the proclamation?',
			user=self.user,
			save_log=False,
		)
		self.assertIn('[1]', out['answer'])
		self.assertAlmostEqual(out['confidence'], 0.8584, places=3)
		self.assertEqual(out['confidence_percent'], 85.8)
		self.assertEqual(len(out['sources']), 1)
		self.assertEqual(out['sources'][0]['relevance'], 0.78)
		self.assertIn('[1]', out['sources'][0]['citation_label'])

	@patch('ai_engine.services.qa.generate_completion')
	@patch('ai_engine.services.qa.semantic_search')
	def test_max_similarity_below_gate_no_llm(self, mock_search, mock_llm):
		ch = MagicMock()
		ch.id = 99
		ch.document_id = 1
		ch.document = MagicMock()
		ch.document.title = 'Doc'
		ch.content = 'Marginal match text.'
		ch.relevance_score = 0.34
		mock_search.return_value = ([ch], 0.34)
		out = generate_answer('What does the tax law say about rates?', user=self.user, save_log=False)
		self.assertEqual(out['answer'], STRICT_NO_RETRIEVAL_ANSWER)
		self.assertEqual(out['sources'], [])
		self.assertEqual(out['confidence'], 0.0)
		mock_llm.assert_not_called()


class ConfidenceFormulaTests(SimpleTestCase):
	def test_calculate_confidence_zero_when_max_below_gate(self):
		from ai_engine.confidence import calculate_confidence

		self.assertEqual(calculate_confidence([0.34], 1), 0.0)

	def test_max_bracket_citation_index(self):
		from ai_engine.confidence import max_bracket_citation_index

		self.assertEqual(max_bracket_citation_index('See [1] and [2].'), 2)
		self.assertEqual(max_bracket_citation_index('No cites'), 0)

	def test_bucketed_confidence_top_band_caps_at_92(self):
		from ai_engine.confidence import calculate_confidence

		self.assertEqual(calculate_confidence([1.0, 1.0, 1.0, 1.0, 1.0], 5), 92.0)

	def test_absence_cap_reduces_high_bucket(self):
		from ai_engine.strict_grounding import cap_confidence_when_absence_indicated

		self.assertEqual(cap_confidence_when_absence_indicated(0.89, 'There is no explicit regulation.'), 0.4)

	def test_absence_cap_ignores_when_no_phrase(self):
		from ai_engine.strict_grounding import cap_confidence_when_absence_indicated

		self.assertEqual(cap_confidence_when_absence_indicated(0.89, 'Article 17 applies.'), 0.89)
