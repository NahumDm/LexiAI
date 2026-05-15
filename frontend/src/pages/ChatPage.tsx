/**
 * Chat Page - Main chat interface with RAG integration
 * Features:
 * - Conversation management
 * - Real-time chat with AI backend
 * - Source citations
 * - Confidence scoring
 * - User feedback system
 */

'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '@/components/layout/Header';
import { ChatSidebar } from '@/components/chat/ChatSidebar';
import { ChatMessage } from '@/components/chat/ChatMessage';
import { ChatInput } from '@/components/chat/ChatInput';
import { GuestBanner } from '@/components/chat/GuestBanner';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useAuth } from '@/contexts/AuthContext';
import { useChat } from '@/contexts/ChatContext';
import { AlertCircle, Loader2 } from 'lucide-react';
import type { Conversation } from '@/lib/api/chat';
import { ChatAPI } from '@/lib/api/chat';

export default function ChatPage() {
	const navigate = useNavigate();
	const { user, isGuest, guestQueriesRemaining, consumeGuestQuery } = useAuth();
	const {
		currentConversation,
		messages,
		isLoading,
		isSendingQuery,
		error,
		setCurrentConversation,
		createConversation,
		loadConversation,
		deleteConversation,
		sendQuery,
		clearMessages,
	} = useChat();

	const [localConversations, setLocalConversations] = useState<Conversation[]>([]);
	const [isLoadingConversations, setIsLoadingConversations] = useState(true);
	const [guestQuotaNotice, setGuestQuotaNotice] = useState<string | null>(null);
	const scrollRef = useRef<HTMLDivElement>(null);

	const refreshConversationSidebar = async (conversationId: number) => {
		try {
			const convResp = await ChatAPI.getConversation(conversationId);
			if (convResp.data) {
				setCurrentConversation(convResp.data);
				setLocalConversations(prev => {
					const filtered = prev.filter(c => c.id !== convResp.data!.id);
					return [convResp.data!, ...filtered];
				});
			}
		} catch (err) {
			console.warn('Failed to refresh conversation metadata:', err);
		}
	};

	// Load conversations when a user session exists (registered users and JWT-backed guests).
	useEffect(() => {
		const loadConversations = async () => {
			try {
				setIsLoadingConversations(true);
				const response = await ChatAPI.getConversations();
				if (response.data) {
					setLocalConversations(response.data);
				} else {
					setLocalConversations([]);
				}
			} catch (err) {
				console.error('Failed to load conversations:', err);
			} finally {
				setIsLoadingConversations(false);
			}
		};

		if (user) {
			loadConversations();
		} else {
			setLocalConversations([]);
			setIsLoadingConversations(false);
		}
	}, [user]);

	// Auto-scroll to bottom on new messages
	useEffect(() => {
		if (scrollRef.current) {
			const scrollArea = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]');
			if (scrollArea) {
				scrollArea.scrollTop = scrollArea.scrollHeight;
			}
		}
	}, [messages]);

	const handleSelectConversation = async (conversation: Conversation) => {
		try {
			await loadConversation(conversation.id);
		} catch (err) {
			console.error('Failed to load conversation:', err);
		}
	};

	const handleNewConversation = () => {
		setCurrentConversation(null);
		clearMessages();
	};

	const handleCreateAndChat = async (query: string) => {
		const title = query.slice(0, 40) + (query.length > 40 ? '...' : '');
		const conversation = await createConversation(title);
		// Pass conversation.id — React state from createConversation is not visible in this closure yet.
		await sendQuery(query, 5, conversation.id);
		await refreshConversationSidebar(conversation.id);
	};

	const handleSendQuery = async (query: string) => {
		setGuestQuotaNotice(null);

		if (isGuest && guestQueriesRemaining <= 0) {
			setGuestQuotaNotice(
				'You have used all 3 guest queries for this session. Create an account to continue with full document-aware chat.'
			);
			return;
		}

		if (!currentConversation) {
			try {
				await handleCreateAndChat(query);
				if (isGuest) consumeGuestQuery();
			} catch (err) {
				console.error('Failed to create conversation or send message:', err);
			}
			return;
		}

		try {
			await sendQuery(query);
			await refreshConversationSidebar(currentConversation.id);
			if (isGuest) consumeGuestQuery();
		} catch (err) {
			console.error('Failed to send query:', err);
		}
	};

	const handleDeleteConversation = async (conversationId: number) => {
		try {
			await deleteConversation(conversationId);
			setLocalConversations(prev => prev.filter(c => c.id !== conversationId));

			if (currentConversation?.id === conversationId) {
				handleNewConversation();
			}
		} catch (err) {
			console.error('Failed to delete conversation:', err);
		}
	};

	return (
		<div className="flex flex-col h-screen bg-background">
				<Header />

				<div className="flex flex-1 overflow-hidden">
					{/* Sidebar */}
					<ChatSidebar
						conversations={localConversations}
						currentConversationId={currentConversation?.id}
						onSelectConversation={handleSelectConversation}
						onNewConversation={handleNewConversation}
						onDeleteConversation={handleDeleteConversation}
						isLoading={isLoadingConversations}
					/>

					{/* Main Chat Area */}
					<div className="flex-1 flex flex-col">
						{/* Guest Banner */}
						{isGuest && (
							<GuestBanner onLoginClick={() => navigate('/login')} />
						)}

						{/* Error Alert */}
						{guestQuotaNotice && (
							<Alert className="m-4 border-warning bg-warning/5">
								<AlertCircle className="h-4 w-4 text-warning" />
								<AlertDescription>{guestQuotaNotice}</AlertDescription>
							</Alert>
						)}

						{error && (
							<Alert variant="destructive" className="m-4">
								<AlertCircle className="h-4 w-4" />
								<AlertDescription>{error}</AlertDescription>
							</Alert>
						)}

						{/* Messages Area */}
						<ScrollArea ref={scrollRef} className="flex-1 p-4">
							<div className="max-w-3xl mx-auto space-y-4">
								{messages.length === 0 && !currentConversation && (
									<div className="text-center py-12">
										<h2 className="text-2xl font-bold mb-2">Welcome to LexiAI</h2>
										<p className="text-muted-foreground">
											{isGuest
												? 'Ask up to 3 questions in guest mode. Sign in to unlock full document-aware chat.'
												: 'Start a new conversation by asking a question about your documents.'}
										</p>
									</div>
								)}

								{messages.map((message, idx) => (
									<ChatMessage
										key={`${message.id}-${idx}`}
										message={message}
										isLoading={isSendingQuery && idx === messages.length - 1 && message.sender === 'assistant'}
									/>
								))}

								{isSendingQuery && messages[messages.length - 1]?.sender === 'user' && (
									<div className="flex flex-col items-center justify-center gap-2 py-4 text-muted-foreground">
										<Loader2 className="h-6 w-6 animate-spin" />
										<span className="text-sm">AI is typing…</span>
									</div>
								)}
							</div>
						</ScrollArea>

						{/* Input Area */}
						<div className="border-t p-4 bg-background">
							<div className="max-w-3xl mx-auto">
								<ChatInput
									onSend={handleSendQuery}
									isLoading={isSendingQuery}
									disabled={isSendingQuery || isLoading || (isGuest && guestQueriesRemaining <= 0)}
									placeholder={
										isGuest && guestQueriesRemaining <= 0
											? 'Guest limit reached. Sign in to continue.'
											: currentConversation
											? 'Ask a question about the documents...'
											: isGuest
												? 'Ask a legal question (3 free tries)...'
												: 'Start typing to create a new conversation...'
									}
								/>
							</div>
						</div>
					</div>
				</div>
			</div>
	);
}
