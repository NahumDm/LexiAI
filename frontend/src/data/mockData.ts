import { Conversation, Document, AdminStats, FeedbackEntry, Message, Citation } from '@/types';

export const mockCitations: Citation[] = [
  {
    id: 'cit-1',
    title: 'Companies Income Tax Act',
    section: 'Section 23(1)(a)',
    source: 'CITA 2004',
    relevance: 0.95,
  },
  {
    id: 'cit-2',
    title: 'Personal Income Tax Act',
    section: 'Section 4(2)',
    source: 'PITA 2011',
    relevance: 0.88,
  },
  {
    id: 'cit-3',
    title: 'Value Added Tax Act',
    section: 'Schedule 1, Item 3',
    source: 'VATA 2007',
    relevance: 0.82,
  },
];

export const mockConversations: Conversation[] = [
  {
    id: 'conv-1',
    title: 'Corporate Tax Deductions',
    createdAt: new Date('2024-12-01'),
    updatedAt: new Date('2024-12-15'),
    userId: '2',
    messages: [
      {
        id: 'msg-1',
        content: 'What expenses can a company deduct from its taxable income in Nigeria?',
        role: 'user',
        timestamp: new Date('2024-12-15T10:00:00'),
      },
      {
        id: 'msg-2',
        content: `Under the Companies Income Tax Act (CITA), companies in Nigeria can deduct various expenses from their taxable income, provided these expenses are incurred wholly, exclusively, and necessarily for the purpose of the business.

**Deductible Expenses Include:**

1. **Operating Expenses**: Rent, utilities, salaries, and wages
2. **Interest Payments**: Interest on loans obtained for business purposes
3. **Depreciation**: Capital allowances on qualifying assets
4. **Bad Debts**: Debts proven to be bad or doubtful
5. **Research & Development**: Expenses on approved R&D activities
6. **Donations**: Contributions to approved funds and institutions (subject to limits)

Note that capital expenditures, fines, and penalties are generally not deductible.`,
        role: 'assistant',
        timestamp: new Date('2024-12-15T10:00:30'),
        citations: [mockCitations[0]],
        confidence: 0.92,
      },
    ],
  },
  {
    id: 'conv-2',
    title: 'VAT Registration Requirements',
    createdAt: new Date('2024-12-10'),
    updatedAt: new Date('2024-12-12'),
    userId: '2',
    messages: [
      {
        id: 'msg-3',
        content: 'When is a business required to register for VAT in Nigeria?',
        role: 'user',
        timestamp: new Date('2024-12-12T14:00:00'),
      },
      {
        id: 'msg-4',
        content: `According to the Value Added Tax Act, every taxable person is required to register for VAT with the Federal Inland Revenue Service (FIRS).

**Registration Requirements:**

1. **Taxable Persons**: All persons and businesses that supply taxable goods or services
2. **Turnover Threshold**: Currently, there is no minimum threshold — all taxable persons must register
3. **Timeline**: Registration must be done within 6 months of commencement of business
4. **Non-Resident Companies**: Must appoint a tax representative for VAT purposes

**Exempt Persons**: Certain persons dealing exclusively in exempt goods/services (medical, educational, agricultural) may be exempt from registration.`,
        role: 'assistant',
        timestamp: new Date('2024-12-12T14:00:45'),
        citations: [mockCitations[2]],
        confidence: 0.89,
      },
    ],
  },
  {
    id: 'conv-3',
    title: 'Personal Income Tax Rates',
    createdAt: new Date('2024-11-20'),
    updatedAt: new Date('2024-11-20'),
    userId: '2',
    messages: [],
  },
];

export const mockDocuments: Document[] = [
  {
    id: 'doc-1',
    name: 'Companies_Income_Tax_Act_2004.pdf',
    size: 2548000,
    source: 'FIRS Official',
    uploadedAt: new Date('2024-06-15'),
    status: 'indexed',
    metadata: {
      pages: 156,
      author: 'Federal Government of Nigeria',
      year: 2004,
      category: 'Primary Legislation',
    },
  },
  {
    id: 'doc-2',
    name: 'Personal_Income_Tax_Act_2011.pdf',
    size: 1892000,
    source: 'FIRS Official',
    uploadedAt: new Date('2024-06-15'),
    status: 'indexed',
    metadata: {
      pages: 98,
      author: 'Federal Government of Nigeria',
      year: 2011,
      category: 'Primary Legislation',
    },
  },
  {
    id: 'doc-3',
    name: 'VAT_Act_Amendment_2023.pdf',
    size: 856000,
    source: 'National Assembly',
    uploadedAt: new Date('2024-11-01'),
    status: 'ocr_processed',
    metadata: {
      pages: 24,
      year: 2023,
      category: 'Amendment',
    },
  },
  {
    id: 'doc-4',
    name: 'FIRS_Circular_2024_001.pdf',
    size: 245000,
    source: 'FIRS Circular',
    uploadedAt: new Date('2024-12-01'),
    status: 'raw',
    metadata: {
      pages: 8,
      year: 2024,
      category: 'Circular',
    },
  },
];

export const mockAdminStats: AdminStats = {
  totalDocuments: 47,
  totalUsers: 234,
  totalQueries: 1892,
  averageRating: 4.2,
  documentsProcessed: 42,
  documentsIndexed: 38,
};

export const mockFeedback: FeedbackEntry[] = [
  {
    id: 'fb-1',
    userId: '2',
    userName: 'John Doe',
    messageId: 'msg-2',
    query: 'What expenses can a company deduct...',
    rating: 5,
    comment: 'Very detailed and helpful response with proper citations.',
    createdAt: new Date('2024-12-15'),
  },
  {
    id: 'fb-2',
    userId: '3',
    userName: 'Jane Smith',
    messageId: 'msg-10',
    query: 'How to calculate withholding tax...',
    rating: 4,
    createdAt: new Date('2024-12-14'),
  },
  {
    id: 'fb-3',
    userId: '4',
    userName: 'Mike Johnson',
    messageId: 'msg-15',
    query: 'Stamp duty on property transfer...',
    rating: 2,
    comment: 'Response was too vague. Needed more specific section references.',
    createdAt: new Date('2024-12-13'),
  },
];

export const sampleAIResponses = [
  {
    content: `Based on the Companies Income Tax Act (CITA) and relevant tax regulations, I can help answer your question.

The tax implications depend on several factors including the nature of the transaction, the parties involved, and applicable tax treaties.

**Key Points:**
1. Corporate entities are subject to Companies Income Tax at 30% (or 20% for small companies)
2. Withholding tax obligations may apply
3. Transfer pricing rules must be considered for related-party transactions

Please provide more specific details about your situation for a more tailored response.`,
    citations: [mockCitations[0]],
    confidence: 0.85,
  },
  {
    content: `Under Nigerian tax law, this matter is governed by specific provisions.

**Relevant Legal Framework:**
- Companies Income Tax Act (CITA)
- Personal Income Tax Act (PITA)
- Relevant tax treaties

The treatment will vary based on residency status and the nature of income involved.`,
    citations: [mockCitations[0], mockCitations[1]],
    confidence: 0.78,
  },
];
