import React from 'react';
import { ChevronRight, Settings, Users, KeyRound, ShieldCheck, LogOut, Rss, Bookmark, Sliders } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { onLinkClick } from '../lib/router';
import { PageHeader } from '../components/ui';
import ThemeToggle from '../components/ThemeToggle';

function Row({ to, Icon, title, hint, tone }) {
  return (
    <a href={to} onClick={onLinkClick(to)} className="flex items-center gap-4 p-4 hover:bg-sunk transition">
      <span className={`w-11 h-11 rounded-2xl flex items-center justify-center shrink-0 ${tone}`}>
        <Icon className="w-5 h-5" aria-hidden="true" />
      </span>
      <span className="flex-1 min-w-0">
        <span className="block font-bold">{title}</span>
        <span className="block text-sm text-muted truncate">{hint}</span>
      </span>
      <ChevronRight className="w-5 h-5 text-muted" aria-hidden="true" />
    </a>
  );
}

/** The More tab on phones: navigation, settings, account. */
export default function MorePage() {
  const { user, logout } = useAuth();
  return (
    <>
      <PageHeader title="More" subtitle={`${user?.username} · ${user?.household_name}`} />
      <div className="card divide-y divide-line/70 overflow-hidden">
        <Row to="/sources" Icon={Rss} title="Sources" hint="Manage news sites and crawl rules" tone="bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300" />
        <Row to="/kept" Icon={Bookmark} title="Kept reading list" hint="Articles saved for later" tone="bg-volt-100 text-volt-800 dark:bg-volt-900/40 dark:text-volt-300" />
        <Row to="/settings/crawl" Icon={Sliders} title="Crawl & retention" hint="Schedules and source limits" tone="bg-moss-100 text-moss-700 dark:bg-moss-900/40 dark:text-moss-300" />
        <Row to="/settings/household" Icon={Users} title="Household" hint="Members and invites" tone="bg-moss-100 text-moss-700 dark:bg-moss-900/40 dark:text-moss-300" />
        <Row to="/settings/security" Icon={ShieldCheck} title="Account security" hint="Password and two-factor" tone="bg-moss-100 text-moss-700 dark:bg-moss-900/40 dark:text-moss-300" />
        {user?.is_superuser && (
          <Row to="/settings/ai" Icon={KeyRound} title="AI and server keys" hint="Anthropic key, sign-up, server keys" tone="bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" />
        )}
        <Row to="/settings" Icon={Settings} title="All settings" hint="Everything in one place" tone="bg-sunk text-muted" />
      </div>
      <div className="mt-5 space-y-4">
        <ThemeToggle />
        <button type="button" onClick={logout} className="btn-soft w-full">
          <LogOut className="w-4 h-4" aria-hidden="true" /> Sign out
        </button>
      </div>
    </>
  );
}
