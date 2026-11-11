import React, { Suspense } from 'react';
import { Loader2, X, ShieldAlert } from 'lucide-react';
import { useAuth } from './context/AuthContext';
import AuthGateway from './components/AuthGateway';
import Shell from './components/Shell';
import { Spinner } from './components/ui';
import { lazyPage } from './appUpdate';
import { matchPath, useLocation } from './lib/router';
import TodayPage from './pages/TodayPage';

// Lazy-loaded pages
const KeptPage = lazyPage(() => import('./pages/KeptPage'));
const SourcesPage = lazyPage(() => import('./pages/SourcesPage'));
const ReaderPage = lazyPage(() => import('./pages/ReaderPage'));
const MorePage = lazyPage(() => import('./pages/MorePage'));
const SettingsPage = lazyPage(() => import('./pages/SettingsPage'));

function SignInNotice() {
  const { signInNotice, dismissSignInNotice } = useAuth();
  if (!signInNotice) return null;
  const { count, addresses } = signInNotice;
  return (
    <div className="banner-warn mb-4 items-center" role="status" data-testid="failed-attempts">
      <ShieldAlert className="w-5 h-5 shrink-0" aria-hidden="true" />
      <p className="flex-1">
        Since you last signed in, {count} wrong password{count === 1 ? ' was' : 's were'} tried on your account
        {addresses > 1 ? ` from ${addresses} places` : ''}. If that wasn&apos;t you, change your password in Settings.
      </p>
      <button type="button" onClick={dismissSignInNotice} aria-label="Dismiss" className="btn-icon w-8 h-8 hover:bg-amber-100/60">
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

function Routes() {
  const { path } = useLocation();
  let params;
  if (path === '/') return <TodayPage />;
  if (path === '/kept') return <KeptPage />;
  if (path === '/sources') return <SourcesPage />;
  if ((params = matchPath('/read/:id', path))) return <ReaderPage id={params.id} />;
  if (path === '/more') return <MorePage />;
  if (path === '/settings' || path.startsWith('/settings/')) return <SettingsPage section={path.split('/')[2]} />;
  return <TodayPage />;
}

export default function App() {
  const { initializing, isAuthenticated } = useAuth();

  if (initializing) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center text-muted">
        <Loader2 className="w-7 h-7 animate-spin" aria-label="Loading" />
      </div>
    );
  }
  if (!isAuthenticated) return <AuthGateway />;

  return (
    <Shell>
      <SignInNotice />
      <Suspense fallback={<Spinner />}>
        <Routes />
      </Suspense>
    </Shell>
  );
}
