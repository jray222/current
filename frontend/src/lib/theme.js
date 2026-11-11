// Light / dark / follow the system. The choice is a per-device convenience, kept in localStorage.
const KEY = 'current:theme';

export function getThemeChoice() {
  try {
    return localStorage.getItem(KEY) || 'system';
  } catch {
    return 'system';
  }
}

export function applyTheme(choice) {
  const dark = choice === 'dark' || (choice === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.classList.toggle('dark', dark);
}

export function setThemeChoice(choice) {
  try {
    if (choice === 'system') localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, choice);
  } catch {
    // Storage blocked: the choice still applies until the page is reloaded.
  }
  applyTheme(choice);
}

/** Follow the system while the choice is "system". */
export function watchSystemTheme() {
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const onChange = () => { if (getThemeChoice() === 'system') applyTheme('system'); };
  media.addEventListener('change', onChange);
  return () => media.removeEventListener('change', onChange);
}
