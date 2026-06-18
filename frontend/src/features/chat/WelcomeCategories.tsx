/**
 * WelcomeCategories — guided category tiles shown on the chat welcome screen.
 *
 * Each tile sends a natural-language query to the real backend so the LangGraph
 * workflow can classify, retrieve KB articles, and reply with grounded steps.
 * This gives users the "click to start" UX of a decision tree while still
 * routing through the actual AI pipeline.
 */

import {
  Mail,
  Lock,
  Laptop,
  Wifi,
  Mic,
  Users,
  Key,
  HelpCircle,
} from 'lucide-react';

interface Category {
  icon: React.ElementType;
  label: string;
  sublabel: string;
  query: string;
  color: string;
}

const CATEGORIES: Category[] = [
  {
    icon: Mail,
    label: 'Outlook / Email',
    sublabel: 'Can\'t send, not receiving, mailbox full',
    query: 'I have an Outlook email issue',
    color: 'text-blue-600 bg-blue-50 border-blue-100',
  },
  {
    icon: Lock,
    label: 'Password & Account',
    sublabel: 'Locked out, forgot password, MFA issues',
    query: 'I have a password or account lockout issue',
    color: 'text-purple-600 bg-purple-50 border-purple-100',
  },
  {
    icon: Wifi,
    label: 'VPN / Network',
    sublabel: 'VPN not connecting, Wi-Fi dropping',
    query: 'I cannot connect to the VPN or my network is having issues',
    color: 'text-green-600 bg-green-50 border-green-100',
  },
  {
    icon: Mic,
    label: 'Audio / Headset',
    sublabel: 'Voice breaks, mic not working, no sound',
    query: 'I have an audio or headset issue during calls',
    color: 'text-orange-600 bg-orange-50 border-orange-100',
  },
  {
    icon: Laptop,
    label: 'Laptop / Hardware',
    sublabel: 'Won\'t start, slow, screen issues',
    query: 'I have a laptop or hardware issue',
    color: 'text-slate-600 bg-slate-50 border-slate-100',
  },
  {
    icon: Key,
    label: 'Access & Licenses',
    sublabel: 'Ruddr, GitHub, Copilot, alias requests',
    query: 'I need help with tool access, a software license, or an email alias',
    color: 'text-indigo-600 bg-indigo-50 border-indigo-100',
  },
  {
    icon: Users,
    label: 'New Joiner Setup',
    sublabel: 'Account setup, onboarding, provisioning',
    query: 'I am a new joiner and need help with account and access setup',
    color: 'text-teal-600 bg-teal-50 border-teal-100',
  },
  {
    icon: HelpCircle,
    label: 'Something Else',
    sublabel: 'Any other IT issue',
    query: 'I have a general IT issue I need help with',
    color: 'text-gray-600 bg-gray-50 border-gray-100',
  },
];

interface WelcomeCategoriesProps {
  onSelect: (query: string) => void;
  disabled?: boolean;
}

export function WelcomeCategories({ onSelect, disabled }: WelcomeCategoriesProps) {
  return (
    <div className="mt-4 w-full max-w-2xl mx-auto">
      <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground text-center">
        Select a topic to get started
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {CATEGORIES.map(({ icon: Icon, label, sublabel, query, color }) => (
          <button
            key={label}
            onClick={() => onSelect(query)}
            disabled={disabled}
            className={`flex flex-col items-start gap-1.5 rounded-xl border p-3 text-left transition-all hover:shadow-md hover:scale-[1.02] active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed ${color}`}
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span className="text-xs font-semibold leading-tight">{label}</span>
            <span className="text-[10px] leading-tight opacity-70">{sublabel}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
