import React from 'react';
import { BookOpen, ExternalLink, RefreshCw } from 'lucide-react';

export default function ArticleBody({
  blocks = [],
  onOpenStory,
  openingStoryUrl = null,
}) {
  if (!blocks || blocks.length === 0) return null;

  return (
    <div className="article-body font-sans text-ink-800 dark:text-ink-200">
      {blocks.map((block, idx) => {
        const key = `block-${idx}`;
        switch (block.t) {
          case 'collection_header':
            return (
              <div
                key={key}
                className="pt-6 pb-4 mb-6 border-b border-cream-200 dark:border-ink-800 flex items-center justify-between"
              >
                <div>
                  <span className="text-[11px] font-black uppercase tracking-widest text-brand-700 dark:text-volt-400">
                    Curated Collection
                  </span>
                  <h2 className="font-serif font-black text-2xl sm:text-3xl text-ink-950 dark:text-cream-50 mt-1">
                    {block.title || 'Stories in this Collection'}
                  </h2>
                </div>
                {block.count && (
                  <span className="text-xs font-mono font-bold bg-cream-200 dark:bg-ink-800 px-3 py-1 rounded-full text-ink-600 dark:text-ink-300">
                    {block.count} stories
                  </span>
                )}
              </div>
            );

          case 'story_card':
            return (
              <div
                key={key}
                className="group relative bg-white dark:bg-ink-900 border border-cream-200 dark:border-ink-800 rounded-2xl p-4 sm:p-5 mb-4 shadow-[0_1px_3px_rgba(0,0,0,0.03)] hover:shadow-md hover:border-brand-500/40 dark:hover:border-volt-500/40 transition-all"
              >
                <div className="flex flex-col-reverse sm:flex-row gap-4 items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <h3
                      onClick={() => onOpenStory && onOpenStory(block)}
                      className="font-serif font-bold text-lg sm:text-xl text-ink-950 dark:text-cream-50 group-hover:text-brand-700 dark:group-hover:text-volt-400 cursor-pointer leading-snug transition-colors mb-2"
                    >
                      {block.title}
                    </h3>

                    {block.summary && (
                      <p className="text-sm text-ink-600 dark:text-ink-300 leading-relaxed line-clamp-3 mb-4">
                        {block.summary}
                      </p>
                    )}

                    <div className="flex items-center gap-2 pt-1 flex-wrap">
                      <button
                        type="button"
                        onClick={() => onOpenStory && onOpenStory(block)}
                        disabled={openingStoryUrl === block.url}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-700 hover:bg-brand-800 text-white dark:bg-volt-500 dark:hover:bg-volt-400 dark:text-ink-950 text-xs font-bold shadow-xs transition-all active:scale-95 disabled:opacity-50"
                      >
                        {openingStoryUrl === block.url ? (
                          <>
                            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            <span>Opening story...</span>
                          </>
                        ) : (
                          <>
                            <BookOpen className="w-3.5 h-3.5" />
                            <span>Read Story</span>
                          </>
                        )}
                      </button>

                      {block.url && (
                        <a
                          href={block.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs font-semibold text-ink-500 dark:text-ink-400 hover:text-ink-800 dark:hover:text-cream-100 py-1.5 px-2.5 rounded-lg hover:bg-cream-100 dark:hover:bg-ink-800 transition-colors"
                          title="Open original story on publisher website"
                        >
                          <span>Original</span>
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                    </div>
                  </div>

                  {block.image && (
                    <div
                      onClick={() => onOpenStory && onOpenStory(block)}
                      className="w-full sm:w-36 h-48 sm:h-28 shrink-0 rounded-xl overflow-hidden bg-cream-200 dark:bg-ink-800 border border-cream-200/60 dark:border-ink-700/60 cursor-pointer shadow-xs"
                    >
                      <img
                        src={block.image}
                        alt=""
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                        loading="lazy"
                        onError={(e) => {
                          e.currentTarget.parentElement.style.display = 'none';
                        }}
                      />
                    </div>
                  )}
                </div>
              </div>
            );
          case 'h2':
          case 'h3':
            return (
              <h2
                key={key}
                className="font-serif font-bold text-xl sm:text-2xl mt-8 mb-3 text-ink-900 dark:text-cream-100 leading-snug"
              >
                {block.x}
              </h2>
            );

          case 'p':
            return (
              <p
                key={key}
                className="text-base sm:text-lg leading-relaxed mb-5 text-ink-800 dark:text-cream-200"
              >
                {block.x}
              </p>
            );

          case 'blockquote':
            return (
              <blockquote
                key={key}
                className="border-l-4 border-volt-500 dark:border-volt-400 pl-4 py-2 my-6 italic text-base sm:text-lg text-ink-700 dark:text-ink-300 bg-cream-100/60 dark:bg-ink-800/50 rounded-r-lg"
              >
                {block.x}
              </blockquote>
            );

          case 'ul':
            return (
              <ul key={key} className="list-disc list-outside pl-6 space-y-2 mb-5 text-base sm:text-lg">
                {(block.items || []).map((item, i) => (
                  <li key={`${key}-item-${i}`} className="leading-relaxed">
                    {item}
                  </li>
                ))}
              </ul>
            );

          case 'ol':
            return (
              <ol key={key} className="list-decimal list-outside pl-6 space-y-2 mb-5 text-base sm:text-lg">
                {(block.items || []).map((item, i) => (
                  <li key={`${key}-item-${i}`} className="leading-relaxed">
                    {item}
                  </li>
                ))}
              </ol>
            );

          case 'figure':
            return (
              <figure key={key} className="my-6">
                <img
                  src={block.src}
                  alt={block.caption || ''}
                  className="rounded-xl w-full object-cover max-h-[500px]"
                  loading="lazy"
                />
                {block.caption && (
                  <figcaption className="text-xs text-ink-500 dark:text-ink-400 mt-2 text-center italic">
                    {block.caption}
                  </figcaption>
                )}
              </figure>
            );

          default:
            return null;
        }
      })}
    </div>
  );
}
