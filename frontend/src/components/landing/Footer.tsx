import React from 'react';
import { Logo } from '@/components/icons/Logo';
import { Mail } from 'lucide-react';

export function Footer() {
  return (
    <footer className="bg-primary py-12">
      <div className="container mx-auto px-6">
        <div className="flex flex-col md:flex-row items-center justify-between gap-8">
          <Logo className="text-primary-foreground" />
          
          <div className="flex flex-col sm:flex-row items-center gap-6 text-primary-foreground/70 text-sm">
            <div className="flex items-center gap-2">
              <Mail className="h-4 w-4" />
              <a href="mailto:supportLexiAI@gmail.com" className="hover:text-secondary transition-colors">
                supportLexiAI@gmail.com
              </a>
            </div>
            <span>© {new Date().getFullYear()} LexiTax AI</span>
          </div>
          
          <div className="flex items-center gap-4 text-primary-foreground/70 text-sm">
            <a href="#" className="hover:text-secondary transition-colors">Privacy Policy</a>
            <a href="#" className="hover:text-secondary transition-colors">Terms of Service</a>
          </div>
        </div>
      </div>
    </footer>
  );
}
