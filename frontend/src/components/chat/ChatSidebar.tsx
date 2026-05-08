import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import type { Conversation } from '@/lib/api/chat';
import { Plus, MessageSquare, Lock, MoreVertical, Trash2 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { format } from 'date-fns';

interface ChatSidebarProps {
  conversations: Conversation[];
  currentConversationId?: number | undefined;
  onSelectConversation: (conversation: Conversation) => void;
  onNewConversation: () => void;
  onDeleteConversation?: (id: number) => void;
  isLoading?: boolean;
}

export function ChatSidebar({
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  isLoading = false,
}: ChatSidebarProps) {
  const { isAuthenticated, isGuest } = useAuth();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [conversationToDelete, setConversationToDelete] = useState<string | null>(null);

  const handleDeleteClick = (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    setConversationToDelete(id);
    setDeleteDialogOpen(true);
  };

  const confirmDelete = () => {
    if (conversationToDelete !== null && onDeleteConversation) {
      onDeleteConversation(conversationToDelete);
    }
    setDeleteDialogOpen(false);
    setConversationToDelete(null);
  };

  if (isGuest) {
    return (
      <div className="w-64 bg-sidebar border-r border-sidebar-border p-4 flex flex-col">
        <div className="flex-1 flex flex-col items-center justify-center text-center">
          <div className="h-12 w-12 rounded-full bg-sidebar-accent flex items-center justify-center mb-4">
            <Lock className="h-6 w-6 text-sidebar-foreground/60" />
          </div>
          <h3 className="font-medium text-sidebar-foreground mb-2">Guest Mode</h3>
          <p className="text-sm text-sidebar-foreground/60 mb-4">
            Sign in to save your conversations and access your history.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-64 bg-sidebar border-r border-sidebar-border flex flex-col">
      <div className="p-4 border-b border-sidebar-border">
        <Button 
          onClick={onNewConversation} 
          variant="sidebar" 
          className="w-full bg-sidebar-accent hover:bg-sidebar-accent/80"
        >
          <Plus className="h-4 w-4 mr-2" />
          New Conversation
        </Button>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {isLoading ? (
            <p className="text-sm text-sidebar-foreground/60 text-center py-8 px-4">
              Loading conversations...
            </p>
          ) : conversations.length === 0 ? (
            <p className="text-sm text-sidebar-foreground/60 text-center py-8 px-4">
              No conversations yet. Start a new one!
            </p>
          ) : (
            conversations.map((conv) => {
              const updatedAt = conv.last_message_at || conv.updated_at || conv.created_at;
              const updatedDate = updatedAt ? new Date(updatedAt) : null;
              return (
                <div
                  key={conv.id}
                  onClick={() => onSelectConversation(conv)}
                  className={`group w-full text-left p-3 rounded-lg transition-colors cursor-pointer flex items-start justify-between ${
                    conv.id === currentConversationId
                      ? 'bg-sidebar-primary text-sidebar-primary-foreground'
                      : 'text-sidebar-foreground hover:bg-sidebar-accent'
                  }`}
                >
                  <div className="flex items-start gap-2 overflow-hidden flex-1">
                    <MessageSquare className="h-4 w-4 mt-0.5 shrink-0" />
                    <div className="overflow-hidden">
                      <p className="text-sm font-medium truncate">{conv.title}</p>
                      <p className="text-xs opacity-60">
                        {updatedDate ? format(updatedDate, 'MMM d, yyyy') : ''}
                      </p>
                    </div>
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                      <button className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-sidebar-accent/50 transition-opacity">
                        <MoreVertical className="h-4 w-4" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="bg-popover border border-border">
                      <DropdownMenuItem 
                        onClick={(e) => handleDeleteClick(e, conv.id)}
                        className="text-destructive focus:text-destructive focus:bg-destructive/10 cursor-pointer"
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              );
            })
          )}
        </div>
      </ScrollArea>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Conversation</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this conversation? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
