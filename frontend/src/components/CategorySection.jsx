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
  ChevronRight,
} from 'lucide-react';
import ArticleRow from './ArticleRow';

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

export default function CategorySection({
  category,
  articles = [],
  onSwipe,
  onOpenReader,
  onSelectCategory,
}) {
  if (!articles || articles.length === 0) return null;

  const Icon = ICON_MAP[category.icon] || Newspaper;

  return (
    <section className="mb-8">
      {/* Editorial Section Header */}
      <div className="flex items-center justify-between pb-2 mb-3 border-b-2 border-brand-700/20 dark:border-volt-500/20">
        <button
          onClick={() => onSelectCategory && onSelectCategory(category.key)}
          className="flex items-center gap-2 group text-left"
        >
          <div className="w-6 h-6 rounded-md bg-brand-700/10 dark:bg-volt-500/10 flex items-center justify-center text-brand-700 dark:text-volt-400">
            <Icon className="w-3.5 h-3.5" />
          </div>
          <h2 className="font-serif font-bold text-lg text-ink-900 dark:text-cream-100 group-hover:text-brand-700 dark:group-hover:text-volt-400 transition-colors">
            {category.label}
          </h2>
          <ChevronRight className="w-4 h-4 text-ink-400 opacity-0 group-hover:opacity-100 transition-opacity" />
        </button>

        <span className="text-xs font-semibold text-ink-500 dark:text-ink-400 bg-cream-200 dark:bg-ink-800 px-2 py-0.5 rounded-full">
          {articles.length} stories
        </span>
      </div>

      {/* Article Rows List */}
      <div className="space-y-2">
        {articles.map((article) => (
          <ArticleRow
            key={article.id}
            article={article}
            onSwipe={onSwipe}
            onOpenReader={onOpenReader}
          />
        ))}
      </div>
    </section>
  );
}
