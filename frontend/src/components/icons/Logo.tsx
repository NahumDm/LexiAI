import React from 'react';

interface LogoProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  showText?: boolean;
}

export function Logo({ className = '', size = 'md', showText = true }: LogoProps) {
  const sizes = {
    sm: 'h-6 w-6',
    md: 'h-8 w-8',
    lg: 'h-12 w-12',
  };

  const textSizes = {
    sm: 'text-lg',
    md: 'text-xl',
    lg: 'text-3xl',
  };

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className={`${sizes[size]} relative`}>
        <svg
          viewBox="0 0 40 40"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="w-full h-full"
        >
          {/* Shield shape */}
          <path
            d="M20 2L4 10V18C4 28 10.5 36.5 20 38C29.5 36.5 36 28 36 18V10L20 2Z"
            fill="currentColor"
            className="text-primary"
          />
          {/* Scale of justice */}
          <path
            d="M20 10V28M14 14H26M12 18L14 14L16 18M24 18L26 14L28 18"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-primary-foreground"
          />
          {/* AI circuit dots */}
          <circle cx="20" cy="22" r="2" fill="currentColor" className="text-secondary" />
          <circle cx="16" cy="24" r="1.5" fill="currentColor" className="text-secondary opacity-70" />
          <circle cx="24" cy="24" r="1.5" fill="currentColor" className="text-secondary opacity-70" />
        </svg>
      </div>
      {showText && (
        <div className="flex flex-col leading-none">
          <span className={`font-serif font-bold ${textSizes[size]} tracking-tight`}>
            Lexi<span className="text-secondary">Tax</span>
          </span>
          <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-sans">
            AI Assistant
          </span>
        </div>
      )}
    </div>
  );
}
