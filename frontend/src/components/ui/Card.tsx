import { type ReactNode } from 'react';
import { clsx } from 'clsx';

interface CardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  gradient?: boolean;
}

export function Card({ children, className, hover, gradient }: CardProps) {
  return (
    <div
      className={clsx(
        'rounded-xl border border-border bg-card p-5 transition-all duration-200',
        hover && 'hover:shadow-md hover:border-primary/20 hover:-translate-y-0.5',
        gradient && 'gradient-brand-subtle border-transparent',
        className
      )}
    >
      {children}
    </div>
  );
}

interface StatCardProps {
  icon: ReactNode;
  label: string;
  value: string;
  trend?: string;
  trendUp?: boolean;
}

export function StatCard({ icon, label, value, trend, trendUp = true }: StatCardProps) {
  return (
    <Card hover className="relative overflow-hidden">
      <div className="absolute -right-4 -top-4 h-24 w-24 rounded-full bg-primary/5" />
      <div className="relative">
        <div className="flex items-center justify-between">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            {icon}
          </div>
          {trend && (
            <span
              className={clsx(
                'flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-medium',
                trendUp ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
              )}
            >
              {trendUp ? '↑' : '↓'} {trend}
            </span>
          )}
        </div>
        <div className="mt-4">
          <p className="text-2xl font-bold tracking-tight text-foreground">{value}</p>
          <p className="mt-0.5 text-sm text-muted-foreground">{label}</p>
        </div>
      </div>
    </Card>
  );
}
