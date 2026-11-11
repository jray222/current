import React from 'react';

export default function ArticleBody({ blocks = [] }) {
  if (!blocks || blocks.length === 0) return null;

  return (
    <div className="article-body font-sans text-ink-800 dark:text-ink-200">
      {blocks.map((block, idx) => {
        const key = `block-${idx}`;
        switch (block.t) {
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
