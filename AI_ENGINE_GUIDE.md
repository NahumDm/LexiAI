# AI Engine Implementation Guide

## Overview

The AI Engine implements a production-ready **Retrieval-Augmented Generation (RAG)** pipeline for LexiAI. It enables users to ask questions about uploaded legal documents and receive grounded answers with citations.

## Architecture

### Core Flow

```
Document Upload
    ↓
Extract Text (existing)
    ↓
Chunk Document (ChunkingService)
    ↓
Generate Embeddings (EmbeddingService) → Store in DB
    ↓
User Query
    ↓
Embed Query (EmbeddingService)
    ↓
Retrieve Relevant Chunks (RetrievalService)
    ↓
Format Context
    ↓
Generate Answer (LLMClient)
    ↓
Save Conversation + Messages
    ↓
Return Answer + Sources
```

### Service Layer

**ai_engine/services/**

- **embedding.py**: Generate and compute similarity between embeddings using sentence-transformers (all-MiniLM-L6-v2)
- **chunking.py**: Split documents into semantic chunks (300–500 tokens per chunk)
- **retrieval.py**: Find top-k relevant chunks using cosine similarity
- **llm_client.py**: Abstract LLM interface (StubLLMClient for dev, OpenAILLMClient pattern for production)
- **rag.py**: Orchestrates the full RAG pipeline

### Models

**DocumentChunk**
Indexes: (document, sequence_index), (document_owner)

Note: the `DocumentChunk` model defines these indexes explicitly in its `Meta.indexes`:
- `models.Index(fields=['document', 'sequence_index'])`
- `models.Index(fields=['document_owner'])`
Use these exact field names or the explicit index name when referencing indexes in migrations or SQL.

**QueryLog**
- Tracks analytics: user, conversation, query, response, latency, tokens
- Enables performance monitoring and usage analysis

## Workflow

### 1. Document Ingestion & Embedding

When a document is uploaded:

```python
# documents/views.py
class DocumentListCreateView:
    def perform_create(self, serializer):
        document = serializer.save()
# Use direct DB similarity search (pgvector)
# For nearest-neighbor queries prefer ordering by a computed distance or annotating with a distance
from django.db.models import F, Func, FloatField

# Option A: order by the cosine distance using a VectorField expression (if supported):
# DocumentChunk.objects.order_by(F('embedding').cosine_distance(query_embedding))[:5]

# Option B: annotate with a computed distance and then order (portable SQL approach):
# This uses the database cosine_distance function and returns a `distance` float you can sort by.
# Replace `cosine_distance` with the exact SQL function available in your pgvector setup.
#
# from django.db.models import Func, F, FloatField, Value
# DocumentChunk.objects.annotate(
#     distance=Func(F('embedding'), Value(query_embedding), function='cosine_distance', output_field=FloatField())
# ).order_by('distance')[:5]

# The key point: don't attempt to use `filter(embedding__cosine_distance=...)` for nearest-neighbor
# ranking — instead annotate or order_by a computed distance and then slice the top-k results.
The `embed_document_chunks` Celery task runs asynchronously:

```python
# ai_engine/tasks.py
@shared_task
def embed_document_chunks(document_id):
    document = Document.objects.get(pk=document_id)
    chunks_data = ChunkingService.chunk_document(document.extracted_text)
    embeddings = EmbeddingService.generate_embeddings_batch(texts)
    # Save DocumentChunk records with embeddings
```

### 2. Chat Query Processing

User initiates a chat query:

```bash
POST /api/v1/chat/{conversation_id}/ask/
{
    "query": "What are the key clauses?",
    "top_k": 5
}
```

The view delegates to RAGPipeline:

```python
# ai_engine/services/rag.py
pipeline = RAGPipeline(llm_client=StubLLMClient())
response = pipeline.process_query(
    query=query,
    conversation=conversation,
    top_k=top_k,
    save_log=True
)
```

RAGPipeline orchestrates:
1. **Embed Query**: Generate embedding for user query
2. **Retrieve**: Find top-k relevant chunks via cosine similarity
3. **Generate**: Call LLM with context + query
4. **Log**: Save QueryLog for analytics
5. **Return**: Answer + sources + metadata

### 3. Permissions & Auth

- Conversation must belong to authenticated user (IsConversationOwner permission)
- Chunks are scoped to documents the user owns
- QueryLogs are isolated per user

## Configuration

### Required Environment Variables (optional)

```env
# For OpenAI integration (future)
OPENAI_API_KEY=sk-...

# Embedding model (hardcoded, can be made configurable)
# EMBEDDING_MODEL=all-MiniLM-L6-v2
```

### Settings

```python
# settings/base.py
INSTALLED_APPS = [
    ...
    'ai_engine.apps.AiEngineConfig',
]
```

### Dependencies

```
sentence-transformers>=2.2.0   # Embedding generation
# Optional:
# openai>=1.0.0               # For OpenAI integration
# pgvector>=0.1.0             # For advanced pgvector features (future)
```

## API Endpoints

### Chat Ask

```
POST /api/v1/chat/{conversation_id}/ask/
Authorization: Bearer <token>

Request:
{
    "query": "What are the payment terms?",
    "top_k": 5
}

Response (200):
{
    "answer": "Based on the provided documents...",
    "sources": [
        {
            "chunk_id": 1,
            "document_title": "Contract A",
            "relevance": 0.945,
            "excerpt": "Payment shall be made within 30 days..."
        }
    ],
    "model_used": "stub-v1",
    "tokens_used": {
        "prompt": 0,
        "completion": 0,
        "total": 0
    }
}

Error (400): Conversation has no document attached
Error (403): Unauthorized access
Error (404): Conversation not found
Error (500): RAG pipeline failed
```

## Service Usage Examples

### Embedding Service

```python
from ai_engine.services.embedding import EmbeddingService

# Generate single embedding
embedding = EmbeddingService.generate_embedding("Some text")

# Generate batch embeddings
embeddings = EmbeddingService.generate_embeddings_batch(["text1", "text2"])

# Compute similarity
similarity = EmbeddingService.cosine_similarity(vec1, vec2)

# Storage/retrieval
as_bytes = EmbeddingService.embedding_to_bytes(embedding)
embedding = EmbeddingService.bytes_to_embedding(as_bytes)
```

### Chunking Service

```python
from ai_engine.services.chunking import ChunkingService

chunks = ChunkingService.chunk_document(
    text="Long document text...",
    target_size=400,
    min_size=300,
    max_size=500
)
# Returns: [{"content": "...", "token_count": 350, "sequence_index": 0}, ...]
```

### Retrieval Service

```python
from ai_engine.services.retrieval import RetrievalService

# Retrieve by document
chunks = RetrievalService.retrieve_relevant_chunks(
    query_text="What are the terms?",
    document=document,
    top_k=5
)

# Retrieve by conversation's document
chunks = RetrievalService.retrieve_by_conversation(
    conversation=conversation,
    query_text="Question?",
    top_k=5
)

# Each result is a RetrievedChunk(chunk, relevance_score)
for retrieved in chunks:
    print(f"Chunk {retrieved.chunk.id}: {retrieved.relevance_score}")
```

### RAG Pipeline

```python
from ai_engine.services.rag import RAGPipeline
from ai_engine.services.llm_client import StubLLMClient

pipeline = RAGPipeline(llm_client=StubLLMClient())
response = pipeline.process_query(
    query="Your question?",
    conversation=conversation,
    top_k=5,
    save_log=True
)

print(response.answer)
print(response.sources)
print(response.model_used)
```

## Testing

### Run Tests

```bash
python manage.py test ai_engine.tests

# Specific test class
python manage.py test ai_engine.tests.ChunkingServiceTests
python manage.py test ai_engine.tests.ChatAPIIntegrationTests
```

### Test Coverage

- **ChunkingServiceTests**: Sentence splitting, chunking logic, sequencing
- **EmbeddingServiceTests**: Embedding generation, similarity, serialization
- **RetrieverIntegrationTests**: Chunk retrieval and ranking
- **ChatAPIIntegrationTests**: Full chat endpoint flow, permissions, error cases
- **QueryLogTests**: Analytics logging

## Production Considerations

### 1. LLM Integration

Replace StubLLMClient with real implementation:

```python
from ai_engine.services.llm_client import OpenAILLMClient

pipeline = RAGPipeline(llm_client=OpenAILLMClient(model="gpt-4"))
response = pipeline.process_query(...)
```

### 2. Vector Database

For large-scale deployments, use pgvector:

```python
# Install pgvector in Postgres
# CREATE EXTENSION vector;

# Update DocumentChunk model field
from pgvector.django import VectorField
embedding = VectorField(dimensions=384)  # Instead of BinaryField

# Use direct DB similarity search
DocumentChunk.objects.filter(
    embedding__cosine_distance=query_embedding
)[:5]
```

### 3. Caching

Cache embeddings and LLM responses:

```python
from django.core.cache import cache

cache_key = f"embedding:{text_hash}"
embedding = cache.get(cache_key) or EmbeddingService.generate_embedding(text)
```

### 4. Rate Limiting

Restrict queries per user/day:

```python
from rest_framework.throttling import UserRateThrottle

class ChatQueryThrottle(UserRateThrottle):
    scope = 'chat_query'
    rate = '100/day'  # 100 queries per day

# settings/base.py
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'chat_query': '100/day',
}
```

### 5. Monitoring

Log and monitor latency, token usage, retrieval quality:

```python
querylogs = QueryLog.objects.filter(user=user)
avg_latency = querylogs.aggregate(Avg('latency_ms'))['latency_ms__avg']
```

## Troubleshooting

### Issue: Embeddings not generated

**Check:**
- Is sentence-transformers installed? `pip list | grep sentence`
- Is Celery running? Check worker logs
- Are documents marked as READY? Check Document.status

**Fix:**
- Install: `pip install sentence-transformers`
- Restart Celery worker
- Manually trigger: `embed_document_chunks.delay(doc_id)`

### Issue: No chunks retrieved

**Check:**
- Are chunks actually created? `DocumentChunk.objects.filter(document=doc).count()`
- Does conversation have a document attached? `conversation.document`
- Are embeddings stored? Check chunk.embedding is not null

**Fix:**
- Re-embed: `embed_document_chunks.delay(doc.pk)`
- Check logs: `QueryLog.objects.latest()` or tail worker logs

### Issue: Chat endpoint returns 500

**Check:**
- Celery running? Check worker
- Is conversation.document set?
- Review logs: `tail lexiai_backend/logs/debug.log`

**Fix:**
- Check pytest output: `python manage.py test ai_engine.tests.ChatAPIIntegrationTests`
- Verify LLM client is initialized

## Future Enhancements

1. **Hybrid Search**: Combine keyword + semantic search
2. **Re-ranking**: Use a cross-encoder to re-rank retrieved chunks
3. **Caching**: Speed up embeddings with Redis caching
4. **Fine-tuning**: Custom embeddings for legal domain
5. **Multi-document**: Search across multiple documents per conversation
6. **Streaming**: Stream LLM response as it generates
7. **Evaluation Metrics**: Track answer quality, user feedback loops
8. **Advanced RAG**: Query expansion, multi-hop reasoning, etc.

## Summary

The AI Engine provides a clean, production-ready RAG implementation that:
- Chunks documents intelligently
- Generates fast embeddings
- Retrieves relevant context semantically
- Abstracts LLM implementation
- Logs analytics
- Maintains strict user isolation
- Passes comprehensive tests
- Follows Django best practices (services, selectors, permissions)
