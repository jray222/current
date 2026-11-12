import React, { useState, useEffect, useCallback } from 'react';
import { ArrowLeft, Bookmark, ExternalLink, RefreshCw, Clock, Share2, Check } from 'lucide-react';
import { getArticle, fetchArticleFulltext, postVote, openArticleByUrl } from '../api';
import { navigate, navigateBack } from '../lib/router';
import AuthImage from '../components/AuthImage';
import ArticleBody from '../components/ArticleBody';
import TextStatus from '../components/TextStatus';

function formatFullDate(dateStr) {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleDateString(undefined, {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

export default function ReaderPage({ id }) {
  const [article, setArticle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fetchingText, setFetchingText] = useState(false);
  const [openingStoryUrl, setOpeningStoryUrl] = useState(null);
  const [isKept, setIsKept] = useState(false);
  const [copied, setCopied] = useState(false);

  const loadArticle = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await getArticle(id);
      setArticle(data);
      setIsKept(data.user_vote === 'keep');

      // Record visual opened state & train interest model implicitly
      try {
        const opened = JSON.parse(localStorage.getItem('current:opened_ids') || '[]');
        if (!opened.includes(data.id)) {
          opened.push(data.id);
          localStorage.setItem('current:opened_ids', JSON.stringify(opened));
        }
        postVote(data.id, 'open').catch(() => {});
      } catch {
        // ignore storage errors
      }

      // Auto-fetch text on open if none yet
      if (data.text_status === 'none') {
        setFetchingText(true);
        try {
          const updated = await fetchArticleFulltext(id);
          setArticle(updated);
        } catch {
          // ignore auto-fetch failure
        } finally {
          setFetchingText(false);
        }
      }
    } catch (err) {
      console.error('Failed to load article:', err);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadArticle();
  }, [loadArticle]);

  const handleOpenStory = async (story) => {
    if (!story?.url) return;
    setOpeningStoryUrl(story.url);
    try {
      const res = await openArticleByUrl({
        url: story.url,
        title: story.title,
        summary: story.summary,
        image_remote_url: story.image,
        source_id: article?.source_id,
        category_id: article?.category_id,
      });
      if (res?.id) {
        navigate(`/reader/${res.id}`);
      } else {
        window.open(story.url, '_blank');
      }
    } catch (err) {
      console.error('Failed to open sub-story:', err);
      window.open(story.url, '_blank');
    } finally {
      setOpeningStoryUrl(null);
    }
  };

  const handleToggleKeep = async () => {
    if (!article) return;
    try {
      const nextVote = isKept ? 'skip' : 'keep';
      await postVote(article.id, nextVote);
      setIsKept(!isKept);
    } catch (err) {
      console.error('Failed to update vote:', err);
    }
  };

  const handleFetchText = async () => {
    if (!article) return;
    setFetchingText(true);
    try {
      const updated = await fetchArticleFulltext(article.id, { force: true });
      setArticle(updated);
    } catch (err) {
      console.error('Failed to extract text:', err);
    } finally {
      setFetchingText(false);
    }
  };

  const handleShare = async () => {
    if (!article) return;
    if (navigator.share) {
      try {
        await navigator.share({
          title: article.title,
          url: article.url,
        });
        return;
      } catch {
        // Fallback to clipboard
      }
    }
    navigator.clipboard.writeText(article.url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="py-24 text-center space-y-3">
        <RefreshCw className="w-6 h-6 animate-spin text-brand-600 dark:text-volt-400 mx-auto" />
        <p className="text-xs text-ink-500 dark:text-ink-400 font-medium">Opening story...</p>
      </div>
    );
  }

  if (!article) {
    return (
      <div className="text-center py-20 space-y-4">
        <p className="text-sm text-ink-600 dark:text-ink-400">Story not found or removed.</p>
        <a href="/" onClick={onLinkClick('/')} className="btn-primary inline-flex gap-2">
          <ArrowLeft className="w-4 h-4" /> Back to Edition
        </a>
      </div>
    );
  }

  return (
    <article className="max-w-3xl mx-auto pb-20">
      {/* Top Action Bar */}
      <div className="sticky top-0 z-20 bg-cream-50/95 dark:bg-ink-950/95 backdrop-blur-md py-3 border-b border-cream-200 dark:border-ink-800 flex items-center justify-between mb-6">
        <button
          type="button"
          onClick={() => navigateBack('/')}
          className="flex items-center gap-1.5 text-xs font-semibold text-ink-700 dark:text-ink-300 hover:text-brand-700 dark:hover:text-volt-400 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Edition</span>
        </button>

        <div className="flex items-center gap-2">
          <button
            onClick={handleToggleKeep}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${
              isKept
                ? 'bg-emerald-600 text-white shadow-xs'
                : 'bg-white dark:bg-ink-800 border border-cream-300 dark:border-ink-700 text-ink-700 dark:text-ink-300 hover:border-emerald-600'
            }`}
          >
            <Bookmark className={`w-3.5 h-3.5 ${isKept ? 'fill-current' : ''}`} />
            <span>{isKept ? 'Saved' : 'Save'}</span>
          </button>

          <button
            onClick={handleShare}
            className="p-1.5 rounded-full bg-white dark:bg-ink-800 border border-cream-300 dark:border-ink-700 text-ink-600 dark:text-ink-300 hover:text-brand-700 dark:hover:text-volt-400 transition-colors"
            title="Share story"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-600" /> : <Share2 className="w-4 h-4" />}
          </button>

          {article.url && (
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 rounded-full bg-white dark:bg-ink-800 border border-cream-300 dark:border-ink-700 text-ink-600 dark:text-ink-300 hover:text-brand-700 dark:hover:text-volt-400 transition-colors"
              title="Open on publisher website"
            >
              <ExternalLink className="w-4 h-4" />
            </a>
          )}
        </div>
      </div>

      {/* Header & Meta */}
      <header className="space-y-4 mb-6">
        <div className="flex items-center gap-2 text-xs text-ink-600 dark:text-ink-400">
          {article.source_favicon ? (
            <img src={article.source_favicon} alt="" className="w-4 h-4 rounded-xs" />
          ) : (
            <div className="w-4 h-4 rounded-xs bg-brand-700/10 text-brand-700 dark:text-volt-400 flex items-center justify-center font-bold text-[9px]">
              {article.source_name?.[0] || 'N'}
            </div>
          )}
          <span className="font-bold text-ink-900 dark:text-cream-100">{article.source_name}</span>
          {article.author && (
            <>
              <span>•</span>
              <span>By {article.author}</span>
            </>
          )}
        </div>

        <h1 className="font-serif font-black text-2xl sm:text-4xl text-ink-950 dark:text-cream-50 leading-tight">
          {article.title}
        </h1>

        <div className="flex items-center gap-1.5 text-xs text-ink-500 dark:text-ink-400">
          <Clock className="w-3.5 h-3.5" />
          <time dateTime={article.published_at || article.discovered_at}>
            {formatFullDate(article.published_at || article.discovered_at)}
          </time>
        </div>
      </header>

      {/* Lead Image */}
      {(article.thumb_path || article.image_remote_url) && (
        <figure className="mb-6 rounded-2xl overflow-hidden bg-cream-200 dark:bg-ink-800">
          {article.thumb_path ? (
            <AuthImage
              path={`/images/${article.thumb_path}`}
              alt={article.title}
              className="w-full max-h-[500px]"
              imgClassName="w-full max-h-[500px] object-cover"
              eager
            />
          ) : (
            <img
              src={article.image_remote_url}
              alt={article.title}
              className="w-full max-h-[500px] object-cover"
              loading="eager"
            />
          )}
        </figure>
      )}

      {/* Text Status Banner */}
      <TextStatus
        textStatus={article.text_status}
        wordCount={article.word_count}
        url={article.url}
        loading={fetchingText}
        onFetchText={handleFetchText}
      />

      {/* Article Content */}
      {article.text_blocks && article.text_blocks.length > 0 ? (
        <ArticleBody
          blocks={article.text_blocks}
          onOpenStory={handleOpenStory}
          openingStoryUrl={openingStoryUrl}
        />
      ) : article.summary ? (
        <div className="prose dark:prose-invert max-w-none text-base sm:text-lg leading-relaxed text-ink-800 dark:text-cream-200">
          <p>{article.summary}</p>
        </div>
      ) : null}

      {/* Footer Attribution */}
      <footer className="mt-12 pt-6 border-t border-cream-200 dark:border-ink-800 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-ink-500 dark:text-ink-400">
        <div>
          Published by <span className="font-semibold text-ink-800 dark:text-cream-200">{article.source_name}</span>
        </div>
        {article.url && (
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-brand-700 dark:text-volt-400 font-semibold hover:underline"
          >
            <span>View original story</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}
      </footer>
    </article>
  );
}
