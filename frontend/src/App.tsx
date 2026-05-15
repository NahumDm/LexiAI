import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { RouteMiddleware } from "@/components/routing/RouteMiddleware";
import { UserRoute, AdminRoute, UserLoginGate, AdminLoginGate } from "@/components/routing/ProtectedRoute";
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
        <RouteMiddleware>
          <ChatProvider>
            <TooltipProvider>
              <Toaster />
              <Sonner />
              <Routes>
                <Route path="/" element={<Index />} />
                <Route
                  path="/login"
                  element={
                    <UserLoginGate>
                      <LoginPage />
                    </UserLoginGate>
                  }
                />
                <Route path="/register" element={<RegisterPage />} />
                <Route
                  path="/chat"
                  element={
                    <UserRoute>
                      <ChatPage />
                    </UserRoute>
                  }
                />
                <Route
                  path="/account"
                  element={
                    <UserRoute>
                      <AccountPage />
                    </UserRoute>
                  }
                />
                <Route
                  path="/admin-login"
                  element={<Navigate to="/admin/login" replace />}
                />
                <Route
                  path="/admin/login"
                  element={
                    <AdminLoginGate>
                      <AdminLoginPage />
                    </AdminLoginGate>
                  }
                />
                <Route
                  path="/admin"
                  element={
                    <AdminRoute>
                      <AdminLayout />
                    </AdminRoute>
                  }
                >
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
        </RouteMiddleware>
      </AuthProvider>
    </BrowserRouter>
  </QueryClientProvider>
);

export default App;
