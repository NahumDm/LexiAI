import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { ChatProvider } from "@/contexts/ChatContext";
import Index from "./pages/Index";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import ChatPage from "./pages/ChatPage";
import AccountPage from "./pages/AccountPage";
import AdminLayout from "./pages/admin/AdminLayout";
import AdminLoginPage from "./pages/admin/AdminLoginPage";
import AdminDashboard from "./pages/admin/AdminDashboard";
import DocumentsPage from "./pages/admin/DocumentsPage";
import UsersPage from "./pages/admin/UsersPage";
import FeedbackPage from "./pages/admin/FeedbackPage";
import LogsPage from "./pages/admin/LogsPage";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

// The /admin/* routes below are the SPA admin DASHBOARD UI (built earlier).
// They are gated by `AdminLayout` which redirects non-staff users. The
// canonical model-CRUD admin still lives at Django's /admin/ — see
// AdminSidebar for the "Open Django Admin" link.
const App = () => (
  <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <AuthProvider>
        <ChatProvider>
          <TooltipProvider>
            <Toaster />
            <Sonner />
            <Routes>
              <Route path="/" element={<Index />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/account" element={<AccountPage />} />
              {/* Separate, isolated entry point for the SPA admin console.
                  The regular /login route is intentionally untouched — users
                  there still land on /chat. Only staff/superusers passing the
                  AdminLoginPage gate proceed to /admin/*. */}
              <Route path="/admin-login" element={<AdminLoginPage />} />
              <Route path="/admin" element={<AdminLayout />}>
                <Route index element={<AdminDashboard />} />
                <Route path="documents" element={<DocumentsPage />} />
                <Route path="users" element={<UsersPage />} />
                <Route path="feedback" element={<FeedbackPage />} />
                <Route path="logs" element={<LogsPage />} />
              </Route>
              <Route path="*" element={<NotFound />} />
            </Routes>
          </TooltipProvider>
        </ChatProvider>
      </AuthProvider>
    </BrowserRouter>
  </QueryClientProvider>
);

export default App;
