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
  const { continueAsGuest, isAuthenticated, isAdminAuthenticated } = useAuth();
  const [showLogin, setShowLogin] = useState(false);
  const [showRegister, setShowRegister] = useState(false);

  // Non-admin authenticated visitors: go to the main app. Admins are sent
  // to `/admin` by `RouteMiddleware` + `getNavigationRedirect` (never mixed
  // with user routes).
  React.useEffect(() => {
    if (!isAuthenticated) return;
    if (isAdminAuthenticated) return;
    navigate('/chat', { replace: true });
  }, [isAuthenticated, isAdminAuthenticated, navigate]);

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
