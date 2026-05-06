import React from 'react';
import { Users, Briefcase, GraduationCap } from 'lucide-react';

const targetUsers = [
  {
    icon: Users,
    title: 'Legal Consumers',
    description: 'Individuals and businesses seeking clear answers to tax-related questions without complex legal jargon.',
  },
  {
    icon: Briefcase,
    title: 'Lawyers',
    description: 'Legal professionals who need quick access to tax law references and citations for their cases.',
  },
  {
    icon: GraduationCap,
    title: 'Law Students',
    description: 'Students researching tax law topics for academic work, exams, and professional preparation.',
  },
];

export function TargetUsersSection() {
  return (
    <section className="py-20 bg-muted/30">
      <div className="container mx-auto px-6">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-serif font-bold text-foreground mb-4">
            Who is <span className="text-secondary">LexiTax AI</span> for?
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Our platform is designed to serve a diverse range of users who need reliable tax law information.
          </p>
        </div>

        <div className="grid sm:grid-cols-3 gap-8 max-w-5xl mx-auto">
          {targetUsers.map((user, index) => (
            <div 
              key={user.title} 
              className="flex flex-col items-center text-center p-8 rounded-2xl bg-background border border-border hover:border-secondary/30 hover:shadow-lg transition-all duration-300"
              style={{ animationDelay: `${index * 0.1}s` }}
            >
              <div className="h-16 w-16 rounded-2xl bg-primary flex items-center justify-center mb-6">
                <user.icon className="h-8 w-8 text-primary-foreground" />
              </div>
              <h3 className="font-serif text-xl font-semibold text-foreground mb-3">
                {user.title}
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                {user.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
