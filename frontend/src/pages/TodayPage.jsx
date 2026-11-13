import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { RefreshCw, Rss, CheckCircle2, SlidersHorizontal } from 'lucide-react';
import {
  getFrontpage,
  getFeed,
  getCategories,
  postVote,
  undoVote,
  crawlAll,
  getFeedSettings,
} from '../api';
import { navigate, onLinkClick } from '../lib/router';
import { saveScrollPosition, restoreScrollPosition } from '../lib/scroll';
import CategoryNav from '../components/CategoryNav';
import LeadStoryCard from '../components/LeadStoryCard';
import CategorySection from '../components/CategorySection';
import ArticleRow from '../components/ArticleRow';
import UndoToast from '../components/UndoToast';
import FeedCustomizeSheet from '../components/FeedCustomizeSheet';
import ArticleActionSheet from '../components/ArticleActionSheet';

export default function TodayPage() {
  const [categories, setCategories] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState('');
  const [frontpage, setFrontpage] = useState(null);
  const [categoryArticles, setCategoryArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [crawling, setCrawling] = useState(false);
  const [isCustomizeOpen, setIsCustomizeOpen] = useState(false);
  const [feedSettings, setFeedSettings] = useState({
    category_order: [],
    excluded_categories: [],
    preview_lines: 2,
  });
  const [openedArticleIds, setOpenedArticleIds] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('current:opened_ids') || '[]');
      return new Set(saved);
    } catch {
      return new Set();
    }
  });
  const [undoState, setUndoState] = useState(null); // { articleId, title, verdict }
  const [actionArticle, setActionArticle] = useState(null);
  const suppressTapUntilRef = useRef(0);
  const [formattedDate] = useState(() =>
    new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })
  );

  const loadData = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    try {
      const [catsRes, fpRes, settingsRes] = await Promise.all([
        getCategories(),
        getFrontpage(),
        getFeedSettings().catch(() => null),
      ]);
      setCategories(catsRes);
      setFrontpage(fpRes);
      if (settingsRes) {
        setFeedSettings(settingsRes);
      }
    } catch (err) {
      console.error('Failed to load front page data:', err);
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Restore scroll position after content finishes loading
  useEffect(() => {
    if (!loading) {
      restoreScrollPosition('/');
    }
  }, [loading]);

  // When a specific category is selected, fetch that category's feed
  useEffect(() => {
    if (!selectedCategory) {
      setCategoryArticles([]);
      return;
    }
    let cancelled = false;
    getFeed(selectedCategory)
      .then((items) => {
        if (!cancelled) setCategoryArticles(items);
      })
      .catch((err) => console.error(err));
    return () => {
      cancelled = true;
    };
  }, [selectedCategory]);

  const handleCrawlNow = async () => {
    setCrawling(true);
    try {
      await crawlAll();
      setTimeout(async () => {
        await loadData();
        setCrawling(false);
      }, 1500);
    } catch {
      setCrawling(false);
    }
  };

  const markArticleOpened = (articleId) => {
    setOpenedArticleIds((prev) => {
      const next = new Set(prev);
      next.add(articleId);
      try {
        localStorage.setItem('current:opened_ids', JSON.stringify(Array.from(next)));
      } catch {
        // ignore
      }
      return next;
    });
    postVote(articleId, 'open').catch(() => {});
  };

  const closeActionSheet = useCallback(() => {
    suppressTapUntilRef.current = Date.now() + 400;
    setActionArticle(null);
  }, []);

  const handleOpenReader = (articleId, { force = false } = {}) => {
    if (!force && (actionArticle || Date.now() < suppressTapUntilRef.current)) return;
    saveScrollPosition('/');
    markArticleOpened(articleId);
    navigate(`/reader/${articleId}`);
  };

  const handleOpenOriginal = (article) => {
    markArticleOpened(article.id);
  };

  const handleSwipe = async (articleId, verdict) => {
    // Find article for undo toast message
    let articleTitle = 'Story';
    if (selectedCategory) {
      const found = categoryArticles.find((a) => a.id === articleId);
      if (found) articleTitle = found.title;
    } else if (frontpage?.lead_story?.id === articleId) {
      articleTitle = frontpage.lead_story.title;
    } else {
      for (const sec of frontpage?.sections || []) {
        const found = sec.articles.find((a) => a.id === articleId);
        if (found) {
          articleTitle = found.title;
          break;
        }
      }
    }

    try {
      await postVote(articleId, verdict);
      setUndoState({
        articleId,
        title: articleTitle,
        verdict,
      });

      // Optimistically remove from state
      if (selectedCategory) {
        setCategoryArticles((prev) => prev.filter((a) => a.id !== articleId));
      } else {
        setFrontpage((prev) => {
          if (!prev) return prev;
          const newLead = prev.lead_story?.id === articleId ? null : prev.lead_story;
          const newSections = prev.sections
            .map((sec) => ({
              ...sec,
              articles: sec.articles.filter((a) => a.id !== articleId),
            }))
            .filter((sec) => sec.articles.length > 0);
          return { lead_story: newLead, sections: newSections };
        });
      }

      if (verdict === 'dislike') {
        if (selectedCategory) {
          getFeed(selectedCategory)
            .then((items) => setCategoryArticles(items))
            .catch(() => {});
        } else {
          loadData({ silent: true });
        }
      }
    } catch (err) {
      console.error('Failed to post swipe vote:', err);
    }
  };

  const handleUndo = async () => {
    if (!undoState) return;
    const { articleId } = undoState;
    setUndoState(null);
    try {
      await undoVote(articleId);
      await loadData();
    } catch (err) {
      console.error('Failed to undo vote:', err);
    }
  };

  // Nav categories filter out user exclusions
  const visibleNavCategories = useMemo(() => {
    const excluded = new Set(feedSettings.excluded_categories || []);
    return categories.filter((c) => !excluded.has(c.key));
  }, [categories, feedSettings.excluded_categories]);

  const hasContent = selectedCategory
    ? categoryArticles.length > 0
    : Boolean(frontpage?.lead_story || frontpage?.sections?.length > 0);

  return (
    <div className="pb-16">
      {/* Editorial Masthead */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 pb-4 mb-4 border-b border-cream-200 dark:border-ink-800">
        <div>
          <div className="flex items-center gap-2 text-[11px] font-black uppercase tracking-widest text-brand-700 dark:text-volt-400">
            <span>{formattedDate}</span>
            <span>•</span>
            <span className="text-ink-400 dark:text-ink-500 font-normal">Curated Edition</span>
          </div>
          <h1 className="font-serif font-black text-3xl sm:text-5xl text-ink-950 dark:text-cream-50 tracking-tight mt-1">
            Today’s Edition
          </h1>
        </div>
        <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
          <button
            type="button"
            onClick={() => setIsCustomizeOpen(true)}
            className="inline-flex items-center gap-1.5 bg-white dark:bg-ink-900 border border-cream-300 dark:border-ink-700 hover:border-brand-500 hover:text-brand-700 dark:hover:border-volt-400 dark:hover:text-volt-400 text-xs font-bold px-3 py-2 rounded-xl text-ink-800 dark:text-cream-100 shadow-xs transition-all active:scale-95"
            title="Customize feed topics and preview text"
          >
            <SlidersHorizontal className="w-3.5 h-3.5 text-brand-600 dark:text-volt-400" />
            <span>Customize</span>
          </button>

          <button
            type="button"
            onClick={handleCrawlNow}
            disabled={crawling}
            className="inline-flex items-center gap-1.5 bg-white dark:bg-ink-900 border border-cream-300 dark:border-ink-700 hover:border-brand-500 hover:text-brand-700 dark:hover:border-volt-400 dark:hover:text-volt-400 text-xs font-bold px-3 py-2 rounded-xl text-ink-800 dark:text-cream-100 shadow-xs transition-all active:scale-95"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-brand-600 dark:text-volt-400 ${crawling ? 'animate-spin' : ''}`} />
            <span>{crawling ? 'Checking…' : 'Sync feeds'}</span>
          </button>
        </div>
      </div>

      {/* Sticky Category Ribbon (Sorted and filtered per user preferences) */}
      <CategoryNav
        categories={visibleNavCategories}
        selectedCategory={selectedCategory}
        onSelectCategory={setSelectedCategory}
      />

      {/* Main Stream Area */}
      <div className="mt-6">
        {loading ? (
          <div className="py-20 text-center space-y-3">
            <RefreshCw className="w-6 h-6 animate-spin text-brand-600 dark:text-volt-400 mx-auto" />
            <p className="text-xs text-ink-500 dark:text-ink-400 font-medium">
              Curating your news edition...
            </p>
          </div>
        ) : !hasContent ? (
          <div className="bg-white dark:bg-ink-900 border border-cream-200 dark:border-ink-800 rounded-3xl p-8 sm:p-12 text-center max-w-lg mx-auto my-12 shadow-xs">
            <div className="w-16 h-16 rounded-3xl bg-brand-50 dark:bg-brand-950/50 text-brand-700 dark:text-volt-400 mx-auto flex items-center justify-center mb-4">
              <CheckCircle2 className="w-8 h-8" />
            </div>
            <h2 className="font-serif font-bold text-2xl text-ink-900 dark:text-cream-100 mb-2">
              You're all caught up!
            </h2>
            <p className="text-xs sm:text-sm text-ink-600 dark:text-ink-400 mb-6 leading-relaxed">
              No unread stories remaining. Swipe on articles as you read to keep training your interest model, or crawl for new updates.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                onClick={handleCrawlNow}
                disabled={crawling}
                className="flex items-center gap-2 bg-brand-700 hover:bg-brand-800 dark:bg-brand-600 dark:hover:bg-brand-500 text-white px-5 py-2.5 rounded-xl text-xs font-semibold shadow-xs transition-colors"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${crawling ? 'animate-spin' : ''}`} />
                <span>Check for updates</span>
              </button>
              <a
                href="/sources"
                onClick={onLinkClick('/sources')}
                className="flex items-center gap-2 bg-cream-200 dark:bg-ink-800 hover:bg-cream-300 dark:hover:bg-ink-700 text-ink-800 dark:text-cream-100 px-5 py-2.5 rounded-xl text-xs font-semibold transition-colors"
              >
                <Rss className="w-3.5 h-3.5" />
                <span>Manage Sources</span>
              </a>
            </div>
          </div>
        ) : selectedCategory ? (
          /* Specific Category Feed View */
          <div className="space-y-2">
            <div className="flex items-center justify-between pb-3 mb-4 border-b border-cream-200 dark:border-ink-800">
              <span className="text-xs font-bold uppercase tracking-wider text-brand-700 dark:text-volt-400">
                {categories.find((c) => c.key === selectedCategory)?.label || selectedCategory}
              </span>
              <span className="text-xs text-ink-500 dark:text-ink-400">
                Swipe right to Keep • Left to Dismiss • Hold for options
              </span>
            </div>
            {categoryArticles.map((article) => (
              <ArticleRow
                key={article.id}
                article={article}
                onSwipe={handleSwipe}
                onLongPress={setActionArticle}
                onOpenReader={handleOpenReader}
                onOpenOriginal={handleOpenOriginal}
                previewLines={feedSettings.preview_lines}
                isOpened={openedArticleIds.has(article.id) || Boolean(article.is_opened)}
              />
            ))}
          </div>
        ) : (
          /* Front Page Editorial View */
          <div>
            {/* Top Stories Lead Hero Card */}
            {frontpage?.lead_story && (
              <LeadStoryCard
                article={frontpage.lead_story}
                onSwipe={handleSwipe}
                onLongPress={setActionArticle}
                onOpenReader={handleOpenReader}
                onOpenOriginal={handleOpenOriginal}
                isOpened={openedArticleIds.has(frontpage.lead_story.id) || Boolean(frontpage.lead_story.is_opened)}
              />
            )}

            {/* Categorized Sections */}
            {frontpage?.sections?.map((section) => (
              <CategorySection
                key={section.category.id}
                category={section.category}
                articles={section.articles}
                onSwipe={handleSwipe}
                onLongPress={setActionArticle}
                onOpenReader={handleOpenReader}
                onOpenOriginal={handleOpenOriginal}
                onSelectCategory={setSelectedCategory}
                previewLines={feedSettings.preview_lines}
                openedArticleIds={openedArticleIds}
              />
            ))}
          </div>
        )}
      </div>

      {/* Feed Customization Sheet */}
      <FeedCustomizeSheet
        isOpen={isCustomizeOpen}
        onClose={() => setIsCustomizeOpen(false)}
        allCategories={categories}
        currentSettings={feedSettings}
        onSettingsSaved={(newSettings) => {
          setFeedSettings(newSettings);
          loadData();
        }}
      />

      {/* Long-Press Article Action Sheet */}
      <ArticleActionSheet
        article={actionArticle}
        onClose={closeActionSheet}
        onDislike={(art) => {
          closeActionSheet();
          handleSwipe(art.id, 'dislike');
        }}
        onKeep={(art) => {
          closeActionSheet();
          handleSwipe(art.id, 'keep');
        }}
        onDismiss={(art) => {
          closeActionSheet();
          handleSwipe(art.id, 'skip');
        }}
        onOpenReader={(id) => {
          closeActionSheet();
          handleOpenReader(id, { force: true });
        }}
      />

      {/* Undo Toast */}
      {undoState && (
        <UndoToast
          message={
            undoState.verdict === 'keep'
              ? 'Saved to Kept'
              : undoState.verdict === 'dislike'
              ? 'Will show fewer like this'
              : 'Dismissed story'
          }
          onUndo={handleUndo}
          onClose={() => setUndoState(null)}
        />
      )}
    </div>
  );
}
