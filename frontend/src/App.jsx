import React, { Suspense } from 'react';
import { Loader2, X, ShieldAlert } from 'lucide-react';
import { useAuth } from './context/AuthContext';
import AuthGateway from './components/AuthGateway';
import Shell from './components/Shell';
import { Spinner } from './components/ui';
import { lazyPage } from './appUpdate';
import { matchPath, useLocation } from './lib/router';
import TodayPage from './pages/TodayPage';
import DecksPage from './pages/DecksPage';
import MorePage from './pages/MorePage';

// Heavier pages load when first opened.
const DeckPage = lazyPage(() => import('./pages/DeckPage'));
const SailPage = lazyPage(() => import('./pages/SailPage'));
const QuizPage = lazyPage(() => import('./pages/QuizPage'));
const NewDeckPage = lazyPage(() => import('./pages/NewDeckPage'));
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
  if (path === '/decks') return <DecksPage />;
  if (path === '/decks/new') return <NewDeckPage />;
  if ((params = matchPath('/decks/:slug', path))) return <DeckPage slug={params.slug} />;
  if (path === '/more') return <MorePage />;
  if (path === '/settings' || path.startsWith('/settings/')) return <SettingsPage section={path.split('/')[2]} />;
  return <TodayPage />;
}

/** Sailing and quizzing take the whole screen, without the navigation. */
function FullScreen({ path }) {
  let params;
  if ((params = matchPath('/decks/:slug/sail', path))) return <SailPage slug={params.slug} />;
  if ((params = matchPath('/decks/:slug/quiz', path))) return <QuizPage slug={params.slug} />;
  return null;
}

export default function App() {
  const { initializing, isAuthenticated } = useAuth();
  const { path } = useLocation();

  if (initializing) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center text-muted">
        <Loader2 className="w-7 h-7 animate-spin" aria-label="Loading" />
      </div>
    );
  }
  if (!isAuthenticated) return <AuthGateway />;

  if (/^\/decks\/[^/]+\/(sail|quiz)$/.test(path)) {
    return (
      <Suspense fallback={<div className="fixed inset-0 bg-black" />}>
        <FullScreen path={path} />
      </Suspense>
    );
  }

  return (
    <Shell>
      <SignInNotice />
      <Suspense fallback={<Spinner />}>
        <Routes />
      </Suspense>
    </Shell>
  );
}
