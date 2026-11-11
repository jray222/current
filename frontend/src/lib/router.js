// A very small history-based router: Current has a handful of pages, so a library isn't worth it.
import { useCallback, useEffect, useState } from 'react';

const listeners = new Set();

export function navigate(path, { replace = false } = {}) {
  if (path === window.location.pathname + window.location.search) return;
  window.history[replace ? 'replaceState' : 'pushState'](null, '', path);
  listeners.forEach((fn) => fn());
  window.scrollTo({ top: 0 });
}

/** The current path and query string; re-renders on navigation, back and forward. */
export function useLocation() {
  const read = () => window.location.pathname + window.location.search;
  const [loc, setLoc] = useState(read);
  useEffect(() => {
    const update = () => setLoc(read());
    listeners.add(update);
    window.addEventListener('popstate', update);
    return () => { listeners.delete(update); window.removeEventListener('popstate', update); };
  }, []);
  const [path, search = ''] = loc.split('?');
  return { path, search: search ? `?${search}` : '', go: useCallback(navigate, []) };
}

/** Matches '/decks/:slug/sail' against a path; returns the params or null. */
export function matchPath(pattern, path) {
  const a = pattern.split('/').filter(Boolean);
  const b = path.split('/').filter(Boolean);
  if (a.length !== b.length) return null;
  const params = {};
  for (let i = 0; i < a.length; i += 1) {
    if (a[i].startsWith(':')) params[a[i].slice(1)] = decodeURIComponent(b[i]);
    else if (a[i] !== b[i]) return null;
  }
  return params;
}

/** A link that navigates without reloading (keeps ctrl/cmd-click working). */
export function onLinkClick(path) {
  return (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
    e.preventDefault();
    navigate(path);
  };
}
