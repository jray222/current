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
  onOpenOriginal,
  onSelectCategory,
  previewLines = 2,
  openedArticleIds = new Set(),
}) {
  if (!articles || articles.length === 0) return null;

  const Icon = ICON_MAP[category.icon] || Newspaper;

  return (
    <section className="mb-10">
      {/* Editorial Section Masthead */}
      <div className="flex items-center justify-between pb-2.5 mb-3.5 border-b border-ink-950/10 dark:border-cream-50/10">
        <button
          onClick={() => onSelectCategory && onSelectCategory(category.key)}
          className="flex items-center gap-2.5 group text-left"
        >
          <div className="w-7 h-7 rounded-lg bg-brand-700/10 dark:bg-volt-500/10 flex items-center justify-center text-brand-700 dark:text-volt-400 group-hover:bg-brand-700 group-hover:text-white transition-all">
            <Icon className="w-4 h-4" />
          </div>
          <h2 className="font-serif font-black text-xl text-ink-950 dark:text-cream-50 group-hover:text-brand-700 dark:group-hover:text-volt-400 tracking-tight transition-colors">
            {category.label}
          </h2>
          <ChevronRight className="w-4 h-4 text-ink-400 opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" />
        </button>

        <span className="text-xs font-semibold text-ink-500 dark:text-ink-400 bg-cream-200/80 dark:bg-ink-800 px-2.5 py-0.5 rounded-full font-mono">
          {articles.length} {articles.length === 1 ? 'story' : 'stories'}
        </span>
      </div>

      {/* Article Rows List */}
      <div className="space-y-2.5">
        {articles.map((article) => (
          <ArticleRow
            key={article.id}
            article={article}
            onSwipe={onSwipe}
            onOpenReader={onOpenReader}
            onOpenOriginal={onOpenOriginal}
            previewLines={previewLines}
            isOpened={openedArticleIds.has(article.id) || Boolean(article.is_opened)}
          />
        ))}
      </div>
    </section>
  );
}
