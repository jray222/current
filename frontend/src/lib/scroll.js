/**
 * Scroll position preservation for smooth navigation across feeds and reader views.
 */

const SCROLL_PREFIX = 'current:scroll:';

export function saveScrollPosition(path = window.location.pathname) {
  try {
    const y = window.scrollY || window.pageYOffset || 0;
    sessionStorage.setItem(`${SCROLL_PREFIX}${path}`, String(Math.round(y)));
  } catch {
    // sessionStorage might be disabled or full
  }
}

export function getSavedScrollPosition(path = window.location.pathname) {
  try {
    const raw = sessionStorage.getItem(`${SCROLL_PREFIX}${path}`);
    if (raw !== null) {
      const val = parseInt(raw, 10);
      return Number.isNaN(val) ? null : val;
    }
  } catch {
    // ignore
  }
  return null;
}

export function clearSavedScrollPosition(path = window.location.pathname) {
  try {
    sessionStorage.removeItem(`${SCROLL_PREFIX}${path}`);
  } catch {
    // ignore
  }
}

export function restoreScrollPosition(path = window.location.pathname) {
  const savedY = getSavedScrollPosition(path);
  if (savedY !== null && savedY > 0) {
    requestAnimationFrame(() => {
      window.scrollTo({ top: savedY, behavior: 'instant' });
    });
    return true;
  }
  return false;
}
