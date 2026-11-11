import React from 'react';
import {
  Flame,
  Globe,
  Flag,
  Landmark,
  Briefcase,
  Cpu,
  FlaskConical,
  HeartPulse,
  Trophy,
  MapPin,
  Palette,
  Newspaper,
} from 'lucide-react';

const ICON_MAP = {
  flame: Flame,
  globe: Globe,
  flag: Flag,
  landmark: Landmark,
  briefcase: Briefcase,
  cpu: Cpu,
  'flask-conical': FlaskConical,
  'heart-pulse': HeartPulse,
  trophy: Trophy,
  'map-pin': MapPin,
  palette: Palette,
  newspaper: Newspaper,
};

export default function CategoryNav({ categories = [], selectedCategory = '', onSelectCategory }) {
  return (
    <nav className="sticky top-0 z-30 bg-cream-50/95 dark:bg-ink-950/95 backdrop-blur-md border-b border-cream-200 dark:border-ink-800 px-4 py-2 overflow-x-auto no-scrollbar">
      <div className="flex items-center gap-1.5 min-w-max max-w-4xl mx-auto">
        <button
          onClick={() => onSelectCategory('')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold tracking-wide transition-all ${
            selectedCategory === ''
              ? 'bg-brand-700 text-white shadow-sm dark:bg-brand-600'
              : 'text-ink-700 dark:text-ink-300 hover:bg-cream-200 dark:hover:bg-ink-800'
          }`}
        >
          <Flame className="w-3.5 h-3.5 text-volt-500" />
          <span>Front Page</span>
        </button>

        {categories.map((cat) => {
          const Icon = ICON_MAP[cat.icon] || Newspaper;
          const isActive = selectedCategory === cat.key;
          return (
            <button
              key={cat.id}
              onClick={() => onSelectCategory(cat.key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                isActive
                  ? 'bg-brand-700 text-white font-semibold shadow-sm dark:bg-brand-600'
                  : 'text-ink-700 dark:text-ink-300 hover:bg-cream-200 dark:hover:bg-ink-800'
              }`}
            >
              <Icon className="w-3.5 h-3.5 opacity-80" />
              <span>{cat.label}</span>
              {cat.unread_count > 0 && (
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                    isActive
                      ? 'bg-white/20 text-white'
                      : 'bg-cream-300 dark:bg-ink-800 text-ink-600 dark:text-ink-300'
                  }`}
                >
                  {cat.unread_count}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
