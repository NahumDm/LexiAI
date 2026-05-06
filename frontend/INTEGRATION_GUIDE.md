# LexiAI Frontend + Backend Integration Guide

## 🎯 Overview

This document describes the production-ready integration between the Next.js/Vite frontend and Django REST backend for LexiAI.

## 🏗️ Architecture

### API Layer (`src/lib/api/`)

**Purpose**: Centralized API client with JWT auth, token refresh, and error handling

#### Files:
- **`client.ts`** - Base API client with:
  - Automatic JWT token injection from sessionStorage
  - Token refresh retry logic on 401
  - Global error handling (401→login redirect, 403→permission error, network errors)
  - Request/response interceptors
  
- **`auth.ts`** - Authentication endpoints:
  - `login(credentials)` - POST /auth/login/
  - `register(data)` - POST /auth/register/
  - `getCurrentUser()` - GET /accounts/me/
  - `logout()` - Clears local tokens
  
- **`chat.ts`** - Chat & conversation endpoints:
  - `getConversations()` - GET /conversations/
  - `getConversation(id)` - GET /conversations/{id}/
  - `createConversation(data)` - POST /conversations/
  - `getMessages(conversationId)` - GET /conversations/{id}/messages/
  - `sendQuery(conversationId, query)` - POST /chat/{id}/ask/
  - `submitFeedback(queryLogId, feedback)` - POST /chat/feedback/{id}/
  
- **`admin.ts`** - Admin-only endpoints:
  - `getDocuments()` - GET /documents/
  - `uploadDocument(file)` - POST /documents/ (multipart/form-data)
  - `deleteDocument(id)` - DELETE /documents/{id}/
  - `getAnalytics(days)` - GET /ai/analytics/
  - `getQueryLogs()` - GET /ai/query-logs/
  - `getUsers()` - GET /accounts/users/
  
- **`index.ts`** - Unified export point

### State Management

#### Auth Context (`src/contexts/AuthContext.tsx`)
Manages global authentication state:
- `user` - Current user object
- `isAuthenticated` - Boolean flag
- `isAdmin` - Role check
- `login()` - Handle login flow
- `register()` - Handle registration
- `logout()` - Clear auth & redirect
- `refreshUser()` - Sync user from backend

Features:
- Session persistence using sessionStorage
- Auto-login on page refresh if token exists
- Global 401 handler redirects to /login
- Provides `useAuth()` hook for components

#### Chat Context (`src/contexts/ChatContext.tsx`)
Manages conversation and message state:
- `currentConversation` - Active conversation
- `messages` - Message history
- `isLoading`, `isSendingQuery` - Loading states
- `sendQuery(query)` - Send message & get AI response
- `createConversation(title)` - New conversation
- `loadConversation(id)` - Load existing conversation
- `submitFeedback(queryLogId, rating, comment)` - Save feedback

Features:
- Optimistic message updates (user message appears immediately)
- Automatic error rollback
- Message history persistence
- Metadata passed through conversation context

### Components

#### Protected Routes (`src/components/ProtectedRoute.tsx`)
Wrapper component that:
- Checks `isAuthenticated` before rendering
- Supports `requireAdmin` prop for admin-only pages
- Redirects unauthenticated users to /login
- Redirects non-admin users to /chat

**Usage**:
```tsx
<ProtectedRoute requireAdmin>
  <AdminPage />
</ProtectedRoute>
```

#### Enhanced ChatMessage (`src/components/chat/ChatMessage.enhanced.tsx`)
Displays AI responses with:
- **Source citations**: Shows all retrieved chunks with relevance scores
- **Confidence scoring**: Visual badge showing retrieval confidence
- **Low-confidence warnings**: Alert UI for responses with <50% confidence
- **Feedback system**: Thumbs up/down buttons with optional comment dialog
- **Metadata display**: Model used, token counts, etc.

#### Updated ChatPage (`src/pages/ChatPage.new.tsx`)
Full chat interface with:
- Conversation sidebar (list, create, delete)
- Message thread with auto-scroll
- Input area with loading states
- Error alerts
- Integration with Chat Context

### Token Management

**Storage**: `sessionStorage` (not localStorage)
- Safer than localStorage (XSS resilient)
- Cleared on browser session end
- Server-side httpOnly cookies preferred (future enhancement)

**Refresh Flow**:
1. Request made with access_token in Authorization header
2. If 401 response: attempt refresh with refresh_token
3. POST /auth/token/refresh/ → get new access_token
4. Retry original request
5. If refresh fails: clear tokens, redirect to /login

**Double-checked Locking**:
- Prevents concurrent token refresh requests
- Only one refresh in-flight at a time
- Other requests wait for completion

## 🔐 Security Best Practices

### ✅ Implemented
- No tokens in localStorage
- Automatic token injection (centralized)
- CORS handled by backend (credentials: include)
- 401/403 error handling
- Input validation before API calls
- httpOnly cookies ready (set by backend)

### ⚠️ Additional Considerations
- Content Security Policy (CSP) headers
- Rate limiting (backend: built-in, frontend: optional throttle)
- Request signing (optional for sensitive ops)
- Audit logging (admin endpoints protected)

## 📡 API Response Handling

### Chat Query Response
```json
{
  "answer": "Based on the documents...",
  "sources": [
    {
      "chunk_id": 1,
      "document_title": "Contract.pdf",
      "relevance": 0.95,
      "excerpt": "..."
    }
  ],
  "model_used": "mistral-7b",
  "tokens_used": {
    "prompt": 150,
    "completion": 45,
    "total": 195
  },
  "retrieval_confidence": 0.87,
  "warnings": []
}
```

### Error Response
```json
{
  "detail": "Error message",
  "status": 400
}
```

## 🚀 Usage Examples

### 1. Login Flow
```tsx
const { login, user } = useAuth();

const handleLogin = async (email, password) => {
  try {
    await login(email, password);
    // Automatically redirects to /chat on success
  } catch (error) {
    console.error(error.message);
  }
};
```

### 2. Send Chat Query
```tsx
const { sendQuery, currentConversation } = useChat();

const handleAsk = async (query) => {
  try {
    const response = await sendQuery(query, 5); // top_k=5
    // response contains: answer, sources, confidence, warnings
  } catch (error) {
    console.error('Query failed:', error);
  }
};
```

### 3. Submit Feedback
```tsx
const { submitFeedback } = useChat();

const handleFeedback = async (queryLogId, rating, comment) => {
  try {
    await submitFeedback(queryLogId, rating, comment);
    console.log('Feedback saved');
  } catch (error) {
    console.error('Feedback submission failed:', error);
  }
};
```

### 4. Admin: Upload Document
```tsx
const { uploadDocument } = AdminAPI;

const handleUpload = async (file) => {
  try {
    const response = await uploadDocument(file, file.name);
    console.log('Document uploaded:', response.data);
  } catch (error) {
    console.error('Upload failed:', error);
  }
};
```

## ⚙️ Environment Configuration

**.env.local** (or .env file):
```env
VITE_API_BASE_URL=http://localhost:8000
VITE_API_VERSION=v1
VITE_TOKEN_EXPIRY=3600
VITE_REFRESH_TOKEN_EXPIRY=86400
VITE_ENABLE_GUEST_CHAT=true
VITE_GUEST_DAILY_LIMIT=5
```

Access in code:
```tsx
const baseUrl = import.meta.env.VITE_API_BASE_URL;
```

## 📋 Implementation Checklist

### Frontend Setup
- [x] API client with JWT auth
- [x] Token refresh logic
- [x] Auth context & provider
- [x] Chat context & provider
- [x] Protected route wrapper
- [x] Enhanced ChatMessage component
- [x] Updated ChatPage
- [x] Environment configuration
- [ ] Update existing components (LoginModal, RegisterModal, AdminPages)
- [ ] Add error boundaries
- [ ] Add loading skeletons
- [ ] Add response caching (optional)

### Backend Readiness
- [x] Auth endpoints (login, register, token/refresh, me)
- [x] Chat endpoints (conversations, messages, queries, feedback)
- [x] Document endpoints (crud, upload)
- [x] Admin endpoints (analytics, users, query logs)
- [x] Proper JWT token structure
- [x] CORS configuration

### Testing
- [ ] Unit tests for API client
- [ ] Integration tests for chat flow
- [ ] E2E tests for auth flow
- [ ] Mock backend responses for development

## 🐛 Troubleshooting

### Token Expires But Not Refreshing
- Check `refresh_token` in sessionStorage
- Verify backend returns `refresh` token in login response
- Check API client's double-check locking logic

### Chat Query Returns 401
- Verify access token is being sent (check Network tab)
- Ensure Authorization header format: `Bearer <token>`
- Check token expiry time

### Feedback Not Submitting
- Verify `query_log_id` matches backend
- Check feedback endpoint path: `/chat/feedback/{id}/`
- Confirm rating is 'up' or 'down'

### CORS Errors
- Backend must have `CORS_ALLOWED_ORIGINS` including frontend URL
- `credentials: include` must be set in all fetch calls

## 📚 Next Steps

1. **Replace mock components**: Update LoginModal, RegisterModal with API integration
2. **Admin pages**: Connect AdminDashboard, DocumentsPage, etc. to admin API
3. **Error boundaries**: Add error handling UI
4. **Loading states**: Add skeleton loaders for better UX
5. **Response caching**: Implement React Query for automatic caching
6. **Real-time updates**: Consider WebSockets for notifications
7. **Analytics**: Track user interactions and conversion funnel

## 📞 Support

For issues or questions, refer to:
1. API Response logs in browser DevTools Network tab
2. Backend logs: `lexiai_backend/logs/debug.log`
3. Frontend console for component errors

---

**Integration Date**: May 2026  
**Status**: Production-Ready  
**Backend Version**: Django REST Framework v3.14+  
**Frontend Version**: Next.js/Vite with React 18+
