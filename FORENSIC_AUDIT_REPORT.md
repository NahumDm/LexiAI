# LexiAI Backend: Forensic Audit Report
## Production-Grade PDF Ingestion & RAG Pipeline Assessment

**Date:** May 10, 2026  
**Scope:** Document extraction, embedding, chunking, retrieval pipeline  
**Status:** ⚠️ **CRITICAL GAPS IDENTIFIED** – 50% implemented, not production-ready

---

## EXECUTIVE SUMMARY

The LexiAI backend has a **solid embedding and retrieval infrastructure** but critical gaps in the **PDF extraction layer** and **bulk ingestion pipeline** prevent it from being production-ready.

**Key Finding:** Bulk document ingestion (admin tax document imports) creates 100+ documents but **never triggers the embedding/chunking layer**. This means:
- ✅ Direct API uploads work (embeddings triggered)
- ❌ Bulk imports create documents with no chunks
- ❌ Semantic retrieval returns zero results for bulk-imported documents
- ❌ RAG pipeline is non-functional for the primary ingestion path

---

## WHAT IS WORKING ✅

### 1. Embedding Infrastructure
- **Model:** `all-MiniLM-L6-v2` (sentence-transformers)
- **Location:** [ai_engine/services/embedding.py](ai_engine/services/embedding.py)
- **Features:**
  - Lazy loading on first use
  - Batch encoding (efficient for 1000s of chunks)
  - Cosine similarity with zero-norm guards
  - Bytes serialization for database storage

### 2. Chunking Service
- **Location:** [ai_engine/services/chunking.py](ai_engine/services/chunking.py)
- **Strategy:** Sentence-based splitting with token bounds (300–500 tokens)
- **Handles:** Oversized sentences, maintains sequence indexing
- **Quality:** Reasonable for MVP (token count is word-count estimate, not tiktoken)

### 3. Retrieval Layer
- **Location:** [ai_engine/services/retrieval.py](ai_engine/services/retrieval.py)
- **Capability:** Cosine similarity ranking, owner/document scoping, top-k retrieval
- **Integration:** Works with conversation context (preferred document vs. user's entire library)
- **Quality:** Production-ready for search given chunks exist

### 4. Background Task (Celery)
- **Task:** `embed_document_chunks` ([ai_engine/tasks.py](ai_engine/tasks.py))
- **Features:**
  - Retry mechanism (max 3 retries, 60s exponential backoff)
  - Empty extraction guard (won't enqueue if no text)
  - Mismatch detection (chunks vs embeddings count)
  - Stale chunk cleanup
  - Comprehensive logging

### 5. Database Models
- **DocumentChunk** ([ai_engine/models.py](ai_engine/models.py)):
  - FK to Document and User (owner scoping)
  - Binary embedding storage
  - Sequence indexing with DB indexes for fast pagination
  - Metadata support (source_document, model version)
- **QueryLog & QueryFeedback:** Analytics/monitoring ready

### 6. Direct Document Upload Flow
- **Endpoint:** `POST /api/v1/documents/`
- **Trigger:** [documents/views.py](documents/views.py) line 25
- **Pattern:** `transaction.on_commit(lambda: embed_document_chunks.delay(document.pk))`
- **Status:** ✅ Correct implementation – embeddings are queued safely after commit

---

## CRITICAL ISSUES ❌

### ISSUE #1: Bulk Ingestion Never Triggers Embeddings
**Severity:** CRITICAL  
**File:** [documents/services.py](documents/services.py) line 145–188  
**Problem:**

The `ingest_tax_documents()` function processes ~1000 documents (admin bulk import) but never enqueues the embedding task:

```python
def ingest_tax_documents(...) -> tuple[int, int, int]:
    for index, path in enumerate(files, start=1):
        content = extract_document_text(path)
        document, created = Document.objects.update_or_create(
            owner=owner,
            title=build_document_title(path),
            defaults={'extracted_text': content, ...}
        )
        # ❌ NO EMBEDDING TRIGGER HERE
        document.source_file.save(path.name, ...)
    return len(files), created_count, updated_count
```

**Impact:**
- Ingestion job completes with 0 chunks created
- `DocumentChunk.objects.filter(document__owner=user)` returns empty queryset
- `RetrievalService.retrieve_relevant_chunks()` finds nothing
- Users ask questions but get no search results
- RAG pipeline fails silently

**Fix:**
Add embedding trigger after document save (with transaction guard to avoid race):

```python
# Inside ingest_tax_documents loop, after document.source_file.save():
if document.extracted_text:
    from django.db import transaction
    from ai_engine.tasks import embed_document_chunks
    # Use closure to capture document.pk at iteration time
    transaction.on_commit(lambda pk=document.pk: embed_document_chunks.delay(pk))
else:
    logger.warning('Skipping embedding for %s: no extracted text', document.title)
```

---

### ISSUE #2: PDF Extraction Pipeline Incomplete
**Severity:** HIGH  
**File:** [documents/services.py](documents/services.py) line 223–240  
**Problem:**

Only 2-tier fallback exists (no OCR support):

```python
def extract_pdf_text(path: Path) -> str:
    try:
        return extract_pdf_text_with_pdfplumber(path)
    except Exception:
        return extract_pdf_text_with_pypdf(path)
```

**Issues:**
1. **Scanned PDFs (images)** → Returns empty string (Amharic documents fail silently)
2. **No extraction quality validation** → Garbled text (CID font corruption) is not detected
3. **No method logging** → Can't tell which extraction succeeded
4. **No max page cap** → 1000-page PDF could run tesseract for hours (DoS risk)

**Expected Behavior:**
- ✅ Native PDF (pdfplumber) → Use if text ≥50 chars and no corruption markers
- ✅ Fallback (pypdf) → Use if pdfplumber failed/insufficient
- ✅ OCR (pytesseract + pdf2image) → Use if native extraction deficient
- ✅ Language support → Amharic + English: `lang='amh+eng'`
- ✅ Page cap → Max 80 pages for OCR (prevent DoS)
- ✅ Logging → Log extraction method used

**Fix:**
Implement 3-tier fallback with validation functions and OCR support (see IMPLEMENTATION section below).

---

### ISSUE #3: Missing Python Dependencies
**Severity:** HIGH  
**File:** [requirements.txt](requirements.txt)  
**Problem:**

OCR dependencies not declared:

```
# ❌ Missing:
pdf2image
pytesseract
```

**Impact:** `import pdf2image` and `import pytesseract` will fail at runtime.

**Fix:**
```
pdf2image>=1.17,<2.0
pytesseract>=0.3,<0.4
```

---

### ISSUE #4: Missing System Dependencies in Docker
**Severity:** HIGH  
**File:** [Dockerfile](Dockerfile)  
**Problem:**

Tesseract language packs not installed:

```dockerfile
RUN apt-get install -y --no-install-recommends build-essential libpq-dev curl
# ❌ Missing:
# - tesseract-ocr
# - tesseract-ocr-amh (Amharic)
# - tesseract-ocr-eng (English)
# - poppler-utils (pdf2image dependency)
```

**Impact:** Container starts but OCR calls will fail with "tesseract not found".

**Fix:**
```dockerfile
RUN apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    tesseract-ocr tesseract-ocr-amh tesseract-ocr-eng \
    poppler-utils
```

---

### ISSUE #5: No Extraction Quality Validation
**Severity:** MEDIUM  
**File:** [documents/services.py](documents/services.py)  
**Problem:**

No functions to detect:
- Empty extraction
- Garbled text (CID markers: `(cid:1234)`)
- Insufficient length (< 50 chars)

**Fix Required:**
```python
def _pdf_native_text_is_deficient(text: str) -> bool:
    """Check if native extraction failed or is corrupted."""
    if not text or len(text.strip()) < 50:
        return True
    if '(cid:' in text:  # Font corruption indicator
        return True
    return False

def _pdf_ocr_text_is_valid(text: str) -> bool:
    """Validate OCR output quality."""
    if not text or len(text.strip()) < 50:
        return False
    if '(cid:' in text:
        return False
    return True
```

---

### ISSUE #6: No Max Page Cap for OCR
**Severity:** MEDIUM  
**File:** Missing from [documents/services.py](documents/services.py)  
**Problem:**

A 500-page PDF will run tesseract for 30+ minutes, blocking the task worker.

**Fix:**
```python
MAX_OCR_PAGES = 80

# In extract_pdf_text_with_ocr():
if len(reader.pages) > MAX_OCR_PAGES:
    logger.warning('PDF too large for OCR: %d pages > %d', len(reader.pages), MAX_OCR_PAGES)
    return ''
```

---

### ISSUE #7: No Extraction Method Logging
**Severity:** LOW  
**File:** [documents/services.py](documents/services.py)  
**Problem:**

Can't audit which extraction method succeeded (needed for debugging Amharic failures).

**Fix:**
Log method used:
```python
logger.info('PDF extraction method=native_pdfplumber path=%s', path.name)
logger.info('PDF extraction method=native_pypdf path=%s', path.name)
logger.info('PDF extraction method=ocr_tesseract path=%s', path.name)
```

---

## IMPLEMENTATION ROADMAP

### Phase 1: Add Dependencies (5 min)
✅ Update [requirements.txt](requirements.txt)  
✅ Update [Dockerfile](Dockerfile)

### Phase 2: Implement OCR Layer (20 min)
✅ Add validation functions  
✅ Implement `extract_pdf_text_with_ocr()`  
✅ Update `extract_pdf_text()` with 3-tier fallback  
✅ Add logging for all methods

### Phase 3: Fix Bulk Ingestion (10 min)
✅ Add embedding trigger in `ingest_tax_documents()` loop  
✅ Add guard for empty extraction  
✅ Add logging for skipped documents

### Phase 4: Testing & Validation (15 min)
✅ pytest documents/ ai_engine/ -v  
✅ Test direct upload → embeddings  
✅ Test bulk ingestion → embeddings  
✅ Test scanned PDF (OCR path)  
✅ Verify retrieval returns chunks

---

## DETAILED IMPLEMENTATION INSTRUCTIONS

### Step 1: Update requirements.txt

Add OCR dependencies:
```
pdf2image>=1.17,<2.0
pytesseract>=0.3,<0.4
```

### Step 2: Update Dockerfile

Replace the apt-get install line:
```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
        tesseract-ocr tesseract-ocr-amh tesseract-ocr-eng \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*
```

### Step 3: Rewrite PDF Extraction in documents/services.py

Replace lines 223–240 with:

```python
MAX_OCR_PAGES = 80


def _pdf_native_text_is_deficient(text: str) -> bool:
    """
    Check if native PDF extraction failed or produced corrupted output.
    Returns True if extraction should not be trusted.
    """
    if not text or len(text.strip()) < 50:
        return True
    # (cid:XXXX) indicates font encoding issues (scanned PDFs often have this)
    if '(cid:' in text:
        return True
    return False


def _pdf_ocr_text_is_valid(text: str) -> bool:
    """Validate OCR output meets minimum quality threshold."""
    if not text or len(text.strip()) < 50:
        return False
    if '(cid:' in text:
        return False
    return True


def extract_pdf_text(path: Path) -> str:
    """
    Extract PDF text with 3-tier fallback:
    1. pdfplumber (fast, good for native PDFs)
    2. pypdf (lighter fallback if pdfplumber fails)
    3. OCR with tesseract (for scanned/image PDFs)
    
    Returns empty string if all methods fail or text is deficient.
    Logs which method succeeded for audit/debugging.
    """
    # Tier 1: pdfplumber
    try:
        text = extract_pdf_text_with_pdfplumber(path)
        if not _pdf_native_text_is_deficient(text):
            logger.info('PDF extraction method=native_pdfplumber path=%s size_chars=%d', path.name, len(text))
            return text
        logger.debug('Pdfplumber extraction deficient for %s (len=%d), trying pypdf', path.name, len(text))
    except Exception as exc:
        logger.debug('Pdfplumber failed for %s: %s', path.name, exc)

    # Tier 2: pypdf
    try:
        text = extract_pdf_text_with_pypdf(path)
        if not _pdf_native_text_is_deficient(text):
            logger.info('PDF extraction method=native_pypdf path=%s size_chars=%d', path.name, len(text))
            return text
        logger.debug('Pypdf extraction deficient for %s (len=%d), trying OCR', path.name, len(text))
    except Exception as exc:
        logger.debug('Pypdf failed for %s: %s', path.name, exc)

    # Tier 3: OCR (tesseract + pdf2image)
    try:
        text = extract_pdf_text_with_ocr(path)
        if _pdf_ocr_text_is_valid(text):
            logger.info('PDF extraction method=ocr_tesseract path=%s size_chars=%d', path.name, len(text))
            return text
        logger.warning('OCR extraction failed quality check for %s (len=%d)', path.name, len(text))
    except Exception as exc:
        logger.error('OCR extraction error for %s: %s', path.name, exc)

    logger.error('All extraction methods failed for %s', path.name)
    return ''


def extract_pdf_text_with_ocr(path: Path) -> str:
    """
    Extract text from scanned or image-based PDFs using OCR.
    Supports Amharic + English via tesseract.
    
    Returns:
        Extracted text or empty string on failure.
    
    Raises:
        ImportError if pdf2image or pytesseract not installed.
        RuntimeError if page count exceeds safety limit.
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError as exc:
        logger.error('OCR dependencies missing: %s', exc)
        raise RuntimeError('pdf2image and pytesseract required for OCR') from exc

    # Safety check: prevent DoS from massive PDFs
    try:
        reader = PdfReader(str(path))
        page_count = len(reader.pages)
    except Exception:
        page_count = 0

    if page_count > MAX_OCR_PAGES:
        logger.warning('PDF exceeds OCR page limit: %d > %d', page_count, MAX_OCR_PAGES)
        raise RuntimeError(f'PDF too large for OCR: {page_count} pages')

    try:
        logger.debug('Starting OCR for %s (%d pages)', path.name, page_count)
        # dpi=150 balances quality and speed for legal documents
        images = convert_from_path(str(path), dpi=150)
        
        extracted_pages = []
        for page_num, image in enumerate(images, start=1):
            try:
                # amh+eng: Amharic + English language support
                text = pytesseract.image_to_string(image, lang='amh+eng')
                if text.strip():
                    extracted_pages.append(text.strip())
                logger.debug('OCR completed page %d/%d for %s', page_num, len(images), path.name)
            except Exception as exc:
                logger.warning('OCR failed on page %d/%d for %s: %s', page_num, len(images), path.name, exc)
                continue

        result = '\n\n'.join(extracted_pages).strip()
        logger.info('OCR extracted %d pages, total size %d chars', len(extracted_pages), len(result))
        return result

    except Exception as exc:
        logger.error('OCR processing failed for %s: %s', path.name, exc)
        raise
```

### Step 4: Fix Bulk Ingestion to Trigger Embeddings

In [documents/services.py](documents/services.py), find the loop inside `ingest_tax_documents()` (~lines 168–184).

Replace:
```python
        if job is not None:
            job.processed_files = index
            job.created_documents = created_count
            job.updated_documents = updated_count
            job.current_file_name = path.name
            job.save(update_fields=['processed_files', 'created_documents', 'updated_documents', 'current_file_name', 'updated_at'])

        document.source_file.save(path.name, ContentFile(path.read_bytes()), save=True)
```

With:
```python
        if job is not None:
            job.processed_files = index
            job.created_documents = created_count
            job.updated_documents = updated_count
            job.current_file_name = path.name
            job.save(update_fields=['processed_files', 'created_documents', 'updated_documents', 'current_file_name', 'updated_at'])

        document.source_file.save(path.name, ContentFile(path.read_bytes()), save=True)

        # Trigger embedding generation after document commit
        if document.extracted_text:
            from django.db import transaction
            from ai_engine.tasks import embed_document_chunks
            # Use closure to capture document.pk at iteration time (avoid late-binding bug)
            transaction.on_commit(lambda pk=document.pk: embed_document_chunks.delay(pk))
        else:
            logger.warning('Document %s (from %s) has empty extracted_text; skipping embedding', 
                           document.title, path.name)
```

### Step 5: Add Extraction Failure Alert

In [ai_engine/tasks.py](ai_engine/tasks.py), enhance the empty extraction guard (~line 23):

Replace:
```python
	if not document.extracted_text:
		logger.warning(f'Document {document_id} has no extracted text')
		return {'created': 0, 'updated': 0}
```

With:
```python
	if not document.extracted_text:
		logger.warning(
			f'Document {document_id} ({document.title}) has no extracted text; '
			f'all extraction methods (pdfplumber/pypdf/OCR) failed'
		)
		# TODO: Send alert to admin dashboard or email
		return {'created': 0, 'updated': 0}
```

---

## VERIFICATION CHECKLIST

After implementing all fixes:

- [ ] `pip install -r requirements.txt` (verify pdf2image, pytesseract install)
- [ ] `docker build -t lexiai:latest .` (verify tesseract packages install)
- [ ] `python manage.py migrate`
- [ ] `pytest documents/ ai_engine/ -v` (run full test suite)
- [ ] **Test 1:** Upload native PDF via API → check DocumentChunk table has rows
- [ ] **Test 2:** Bulk ingest tax_doc → check DocumentChunk count matches expected
- [ ] **Test 3:** Create scanned PDF in tax_doc, ingest → verify OCR method in logs
- [ ] **Test 4:** Query `/api/v1/chat/ask/` with question → verify retrieval returns chunks
- [ ] Check application logs for extraction methods (pdfplumber/pypdf/ocr_tesseract)
- [ ] Verify no "(cid:" markers in DocumentChunk.content

---

## ESTIMATED EFFORT

| Task | Time | Complexity |
|------|------|-----------|
| Update dependencies | 5 min | Trivial |
| Implement OCR layer | 20 min | Moderate |
| Fix ingestion trigger | 10 min | Simple |
| Testing & validation | 15 min | Moderate |
| **TOTAL** | **50 min** | MVP-grade |

---

## PRODUCTION READINESS SUMMARY

| Component | Status | Notes |
|-----------|--------|-------|
| Embedding Service | ✅ Ready | No changes needed |
| Chunking Service | ✅ Ready | Token estimate is approximate but sufficient |
| Retrieval Service | ✅ Ready | Works if chunks exist |
| Direct API Upload | ✅ Ready | Correctly triggers embeddings |
| **Bulk Ingestion** | ❌ Broken | Does NOT trigger embeddings |
| **PDF Extraction** | ⚠️ Incomplete | Missing OCR and validation |
| **Dependencies** | ❌ Missing | OCR deps not in requirements |
| **Docker** | ❌ Missing | Tesseract packages not installed |

**Current Status:** 50% implemented  
**Blocker:** None (all fixes are straightforward)  
**Go-Live Risk:** HIGH until bulk ingestion embeddings are fixed  

---

## RECOMMENDATION

**Implement all fixes before UAT.** The changes are low-risk and take ~50 minutes. Without them:
- Users bulk-import documents → no chunks exist → semantic search returns nothing
- Direct uploads work fine (hidden from users until bulk import is tested)
- System appears broken in production

Prioritize:
1. **Bulk ingestion embedding trigger** (CRITICAL)
2. **OCR pipeline** (HIGH)
3. **Dependencies** (BLOCKER)

---

## CONTACTS FOR QUESTIONS

- **Architecture:** See [ai_engine/](ai_engine/) module structure and [documents/services.py](documents/services.py)
- **Testing:** [documents/tests.py](documents/tests.py) and [ai_engine/tests.py](ai_engine/tests.py)
- **Logging:** Check application logs for "extraction method=" entries

---

**Report Generated:** May 10, 2026  
**Backend Django Version:** 6.0+  
**Celery Version:** 5.4+  
**Python:** 3.12+
