import React from 'react';
import { Button } from '@/components/ui/button';
import { ArrowRight, Scale, Shield, Brain } from 'lucide-react';

interface HeroSectionProps {
  onLoginClick: () => void;
  onRegisterClick: () => void;
  onGuestClick: () => void;
}

export function HeroSection({ onLoginClick, onRegisterClick, onGuestClick }: HeroSectionProps) {
  return (
    <section className="hero-gradient min-h-[90vh] flex items-center relative overflow-hidden">
      {/* Background pattern */}
      <div className="absolute inset-0 opacity-10">
        <div className="absolute top-20 left-10 w-64 h-64 bg-white rounded-full blur-3xl" />
        <div className="absolute bottom-20 right-10 w-96 h-96 bg-secondary rounded-full blur-3xl" />
      </div>

      <div className="container mx-auto px-6 py-20 relative z-10">
        <div className="max-w-4xl mx-auto text-center">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/10 border border-white/20 mb-8 animate-fade-in">
            <Brain className="h-4 w-4 text-secondary" />
            <span className="text-sm text-white/90">AI-Powered Legal Research</span>
          </div>

          {/* Headline */}
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-serif font-bold text-white mb-6 animate-slide-up leading-tight">
            Tax Law Research,{' '}
            <span className="text-secondary">Simplified</span>
          </h1>

          <p className="text-lg sm:text-xl text-white/80 mb-10 max-w-2xl mx-auto animate-slide-up leading-relaxed">
            Get instant, citation-backed answers to your Ethiopian tax law questions. 
            Powered by AI, grounded in authoritative legal documents.
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16 animate-slide-up">
            <Button 
              size="xl" 
              variant="gold" 
              onClick={onRegisterClick}
              className="min-w-[200px]"
            >
              Get Started Free
              <ArrowRight className="ml-2 h-5 w-5" />
            </Button>
            <Button 
              size="xl" 
              variant="heroOutline" 
              onClick={onGuestClick}
              className="min-w-[200px]"
            >
              Try as Guest
            </Button>
          </div>

          {/* Feature highlights */}
          <div className="grid sm:grid-cols-3 gap-6 max-w-3xl mx-auto">
            <div className="flex flex-col items-center gap-3 p-4 rounded-xl bg-white/5 border border-white/10 animate-slide-up">
              <div className="h-12 w-12 rounded-full bg-secondary/20 flex items-center justify-center">
                <Scale className="h-6 w-6 text-secondary" />
              </div>
              <h3 className="font-medium text-white">Legal Accuracy</h3>
              <p className="text-sm text-white/60">Responses backed by official tax law documents</p>
            </div>
            <div className="flex flex-col items-center gap-3 p-4 rounded-xl bg-white/5 border border-white/10 animate-slide-up" style={{ animationDelay: '0.1s' }}>
              <div className="h-12 w-12 rounded-full bg-secondary/20 flex items-center justify-center">
                <Brain className="h-6 w-6 text-secondary" />
              </div>
              <h3 className="font-medium text-white">AI-Powered</h3>
              <p className="text-sm text-white/60">Natural language understanding for complex queries</p>
            </div>
            <div className="flex flex-col items-center gap-3 p-4 rounded-xl bg-white/5 border border-white/10 animate-slide-up" style={{ animationDelay: '0.2s' }}>
              <div className="h-12 w-12 rounded-full bg-secondary/20 flex items-center justify-center">
                <Shield className="h-6 w-6 text-secondary" />
              </div>
              <h3 className="font-medium text-white">Trusted Sources</h3>
              <p className="text-sm text-white/60">Citations from verified legal documents</p>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom wave */}
      <div className="absolute bottom-0 left-0 right-0">
        <svg viewBox="0 0 1440 120" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path 
            d="M0 120L60 110C120 100 240 80 360 70C480 60 600 60 720 65C840 70 960 80 1080 85C1200 90 1320 90 1380 90L1440 90V120H1380C1320 120 1200 120 1080 120C960 120 840 120 720 120C600 120 480 120 360 120C240 120 120 120 60 120H0Z" 
            fill="hsl(var(--background))"
          />
        </svg>
      </div>
    </section>
  );
}
