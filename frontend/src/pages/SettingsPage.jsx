import React from 'react';
import { KeyRound, ShieldCheck, Users } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { onLinkClick } from '../lib/router';
import { PageHeader } from '../components/ui';
import HouseholdSection from '../components/settings/HouseholdSection';
import SecuritySection from '../components/settings/SecuritySection';
import AISection from '../components/settings/AISection';

const SECTIONS = [
  { id: 'household', label: 'Household', Icon: Users, Component: HouseholdSection },
  { id: 'security', label: 'Security', Icon: ShieldCheck, Component: SecuritySection },
  { id: 'ai', label: 'AI & server', Icon: KeyRound, Component: AISection, ownerOnly: true },
];

export default function SettingsPage({ section }) {
  const { user } = useAuth();
  const visible = SECTIONS.filter((s) => !s.ownerOnly || user?.is_superuser);
  const current = visible.find((s) => s.id === section) || visible[0];
  const { Component } = current;

  return (
    <div className="max-w-3xl mx-auto">
      <PageHeader title="Settings" subtitle={user?.household_name} />
      <nav aria-label="Settings sections" className="flex gap-2 overflow-x-auto no-scrollbar -mx-4 px-4 sm:mx-0 sm:px-0 sm:flex-wrap pb-1 mb-5">
        {visible.map(({ id, label, Icon }) => (
          <a key={id} href={`/settings/${id}`} onClick={onLinkClick(`/settings/${id}`)}
            aria-current={current.id === id ? 'page' : undefined}
            className={`chip !text-sm !px-4 !py-2 ${current.id === id ? 'chip-on' : ''}`}>
            <Icon className="w-4 h-4" aria-hidden="true" /> {label}
          </a>
        ))}
      </nav>
      <Component />
    </div>
  );
}
