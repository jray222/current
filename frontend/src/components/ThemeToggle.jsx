import React, { useState } from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';
import { getThemeChoice, setThemeChoice } from '../lib/theme';

const OPTIONS = [
  { id: 'light', label: 'Light', Icon: Sun },
  { id: 'system', label: 'Auto', Icon: Monitor },
  { id: 'dark', label: 'Dark', Icon: Moon },
];

/** Light / auto / dark, remembered on this device. */
export default function ThemeToggle() {
  const [choice, setChoice] = useState(getThemeChoice);
  const pick = (id) => { setThemeChoice(id); setChoice(id); };
  return (
    <div className="grid grid-cols-3 gap-1 rounded-2xl bg-sunk p-1" role="radiogroup" aria-label="Theme">
      {OPTIONS.map(({ id, label, Icon }) => (
        <button key={id} type="button" role="radio" aria-checked={choice === id} onClick={() => pick(id)}
          className={`flex items-center justify-center gap-1.5 rounded-xl py-2 text-xs font-bold transition cursor-pointer ${
            choice === id ? 'bg-surface text-ink shadow-soft' : 'text-muted hover:text-ink'}`}>
          <Icon className="w-4 h-4" aria-hidden="true" /> {label}
        </button>
      ))}
    </div>
  );
}
