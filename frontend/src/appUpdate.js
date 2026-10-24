// After Dose is updated, a page that is still running the old app asks for
// code files that the update replaced, and that page would go blank. When that
// happens, reload once so the browser picks up the new version.
import { lazy } from 'react';

const KEY = 'dose:reloaded-for-update';
const AGAIN_AFTER_MS = 30_000; // never loop if a reload doesn't help

/** Reloads the page unless it already did so moments ago. True if reloading. */
export function reloadForUpdate() {
  try {
    const last = Number(sessionStorage.getItem(KEY)) || 0;
    if (Date.now() - last < AGAIN_AFTER_MS) return false;
    sessionStorage.setItem(KEY, String(Date.now()));
  } catch {
    // Storage blocked: reload anyway; the error screen still stops a loop.
  }
  window.location.reload();
  return true;
}

/** React.lazy for a page or panel, reloading once if its file is gone. */
export const lazyPage = (load) => lazy(() => load().catch((err) => {
  if (reloadForUpdate()) return new Promise(() => {}); // the page is reloading
  throw err;
}));

// Vite fires this when a file a lazy page needs fails to load.
export function reloadWhenFilesAreGone() {
  window.addEventListener('vite:preloadError', (e) => {
    if (reloadForUpdate()) e.preventDefault();
  });
}
