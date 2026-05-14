import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '@/components/layout/Header';
import { HeroSection } from '@/components/landing/HeroSection';
import { FeaturesSection } from '@/components/landing/FeaturesSection';
import { TargetUsersSection } from '@/components/landing/TargetUsersSection';
import { Footer } from '@/components/landing/Footer';
import { LoginModal } from '@/components/auth/LoginModal';
import { RegisterModal } from '@/components/auth/RegisterModal';
import { useAuth } from '@/contexts/AuthContext';

export default function LandingPage() {
  const navigate = useNavigate();
  const { continueAsGuest, isAuthenticated, isAdminUser } = useAuth();
  const [showLogin, setShowLogin] = useState(false);
  const [showRegister, setShowRegister] = useState(false);

  // SESSION ISOLATION
  // ----------------------------------------------------------------
  // Auto-routing logic for visitors who already have a session.
  //
  //   - Admins on `/` MUST NOT be silently bounced to `/admin`.
  //     Doing so was the original auth-leakage bug — a localStorage
  //     JWT from `/admin-login` would auto-authenticate the admin
  //     into the user app the moment they typed `/`. The dedicated
  //     guard inside `AuthContext` now tears down the admin session
  //     and redirects to `/login` whenever an admin lands on a
  //     user route (`/`, `/chat`, `/account`). We INTENTIONALLY do
  //     nothing for admins here so the centralised guard owns the
  //     teardown path and there is no race between two `navigate()`
  //     calls.
  //   - Non-admin authenticated users go straight to `/chat`, their
  //     post-login destination.
  React.useEffect(() => {
    if (!isAuthenticated) return;
    if (isAdminUser) return;
    navigate('/chat', { replace: true });
  }, [isAuthenticated, isAdminUser, navigate]);

  const handleGuestClick = async () => {
    try {
      await continueAsGuest();
      navigate('/chat');
    } catch {
      // AuthContext sets error; stay on landing page
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header overlays the hero */}
      <div className="absolute top-0 left-0 right-0 z-50">
        <Header 
          onLoginClick={() => setShowLogin(true)}
          onRegisterClick={() => setShowRegister(true)}
          variant="landing"
        />
      </div>

      <HeroSection
        onLoginClick={() => setShowLogin(true)}
        onRegisterClick={() => setShowRegister(true)}
        onGuestClick={handleGuestClick}
      />

      <FeaturesSection />

      <TargetUsersSection />

      <Footer />

      {/* Auth Modals */}
      <LoginModal
        open={showLogin}
        onOpenChange={setShowLogin}
        onSwitchToRegister={() => {
          setShowLogin(false);
          setShowRegister(true);
        }}
      />
      <RegisterModal
        open={showRegister}
        onOpenChange={setShowRegister}
        onSwitchToLogin={() => {
          setShowRegister(false);
          setShowLogin(true);
        }}
      />
    </div>
  );
}
