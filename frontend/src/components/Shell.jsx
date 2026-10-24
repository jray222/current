import React from 'react';
import { Sun, Layers, Menu, Plus, Settings, LogOut } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useLocation, onLinkClick } from '../lib/router';
import { Wordmark } from './Brand';
import ThemeToggle from './ThemeToggle';

const TABS = [
  { to: '/', label: 'Today', Icon: Sun, match: (p) => p === '/' },
  { to: '/decks', label: 'Decks', Icon: Layers, match: (p) => p.startsWith('/decks') },
  { to: '/more', label: 'More', Icon: Menu, match: (p) => p === '/more' || p.startsWith('/settings') },
];

const EXTRA = [
  { to: '/decks/new', label: 'New deck', Icon: Plus, match: (p) => p === '/decks/new', ownerOnly: true },
  { to: '/settings', label: 'Settings', Icon: Settings, match: (p) => p.startsWith('/settings') },
];

function SideLink({ to, label, Icon, active }) {
  return (
    <a href={to} onClick={onLinkClick(to)} aria-current={active ? 'page' : undefined}
      className={`flex items-center gap-3 rounded-2xl px-4 py-3 font-bold transition ${
        active ? 'bg-brand-600 text-white shadow-pop' : 'text-muted hover:bg-sunk hover:text-ink'}`}>
      <Icon className="w-5 h-5" aria-hidden="true" />
      {label}
    </a>
  );
}

/** Side nav on desktop, bottom tab bar on phones. */
export default function Shell({ children }) {
  const { path } = useLocation();
  const { user, logout } = useAuth();
  const activeTab = TABS.find((t) => t.match(path));
  const extra = EXTRA.filter((e) => !e.ownerOnly || user?.is_superuser);

  return (
    <div className="min-h-screen bg-cream">
      <aside className="hidden lg:flex fixed inset-y-0 left-0 w-64 flex-col bg-surface border-r border-line/70 p-5 z-30">
        <a href="/" onClick={onLinkClick('/')} className="px-2 py-1 mb-6" aria-label="Dose home">
          <Wordmark />
        </a>
        <nav aria-label="Main" className="space-y-1.5">
          {TABS.filter((t) => t.to !== '/more').map((t) => (
            <SideLink key={t.to} {...t} active={activeTab === t && !extra.some((e) => e.match(path))} />
          ))}
          <div className="pt-4 mt-4 border-t border-line/70 space-y-1.5">
            {extra.map((t) => <SideLink key={t.to} {...t} active={t.match(path)} />)}
          </div>
        </nav>
        <div className="mt-auto space-y-3">
          <ThemeToggle />
          <div className="flex items-center gap-3 rounded-2xl bg-sunk p-3">
            <div className="w-10 h-10 rounded-full bg-moss-500 text-white font-display font-semibold flex items-center justify-center uppercase" aria-hidden="true">
              {user?.username?.[0]}
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-bold truncate">{user?.username}</p>
              <p className="text-xs text-muted truncate">{user?.household_name}</p>
            </div>
            <button type="button" onClick={logout} aria-label="Sign out" title="Sign out" className="btn-icon text-muted hover:text-brand-600 hover:bg-surface">
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </aside>

      <main className="lg:pl-64 pb-28 lg:pb-12 pt-safe">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-10 pt-5 sm:pt-8">
          {children}
        </div>
      </main>

      <nav aria-label="Main" className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-surface/95 backdrop-blur border-t border-line/70 pb-safe">
        <ul className="grid grid-cols-3 max-w-md mx-auto px-2 pt-2 pb-2">
          {TABS.map(({ to, label, Icon }) => {
            const active = activeTab?.to === to;
            return (
              <li key={to}>
                <a href={to} onClick={onLinkClick(to)} aria-current={active ? 'page' : undefined}
                  className={`flex flex-col items-center gap-0.5 py-1.5 rounded-2xl text-xs font-bold transition ${
                    active ? 'text-brand-600 dark:text-brand-300' : 'text-muted'}`}>
                  <span className={`flex items-center justify-center w-14 h-8 rounded-full transition ${active ? 'bg-brand-100 dark:bg-brand-900/50' : ''}`}>
                    <Icon className="w-6 h-6" aria-hidden="true" strokeWidth={active ? 2.5 : 2} />
                  </span>
                  {label}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
