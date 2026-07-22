import React from 'react';
import { MessageSquare, History, FileText, Sparkles, BookOpen, Shield } from 'lucide-react';

const features = [
  {
    icon: MessageSquare,
    title: 'Natural Language Queries',
    description: 'Ask questions in plain English. Our AI understands context and legal terminology.',
  },
  {
    icon: FileText,
    title: 'Citation-Backed Answers',
    description: 'Every response includes references to specific sections of tax law documents.',
  },
  {
    icon: History,
    title: 'Conversation History',
    description: 'Save and continue your research sessions. Never lose track of important discussions.',
  },
  {
    icon: Sparkles,
    title: 'Confidence Indicators',
    description: 'Transparency about the AI\'s certainty level for each response.',
  },
  {
    icon: BookOpen,
    title: 'Comprehensive Coverage',
    description: 'Access to a vast library of Ethiopian tax laws, regulations, and guidelines.',
  },
  {
    icon: Shield,
    title: 'Secure & Private',
    description: 'Your queries and research are kept confidential and secure.',
  },
];

export function FeaturesSection() {
  return (
    <section className="py-20 bg-background">
      <div className="container mx-auto px-6">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-serif font-bold text-foreground mb-4">
            Research Made <span className="text-secondary">Intelligent</span>
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            LexiTax AI combines advanced natural language processing with authoritative legal sources
            to deliver accurate, actionable insights.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-8 max-w-6xl mx-auto">
          {features.map((feature, index) => (
            <div 
              key={feature.title} 
              className="legal-card group hover:border-secondary/30 transition-all duration-300"
              style={{ animationDelay: `${index * 0.1}s` }}
            >
              <div className="h-12 w-12 rounded-xl bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-secondary/20 transition-colors">
                <feature.icon className="h-6 w-6 text-primary group-hover:text-secondary transition-colors" />
              </div>
              <h3 className="font-serif text-xl font-semibold text-foreground mb-2">
                {feature.title}
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
