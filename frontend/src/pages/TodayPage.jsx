import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Rss, CheckCircle2 } from 'lucide-react';
import { getFrontpage, getFeed, getCategories, postVote, undoVote, crawlAll } from '../api';
import { navigate, onLinkClick } from '../lib/router';
import CategoryNav from '../components/CategoryNav';
import LeadStoryCard from '../components/LeadStoryCard';
import CategorySection from '../components/CategorySection';
import ArticleRow from '../components/ArticleRow';
import UndoToast from '../components/UndoToast';

export default function TodayPage() {
  const [categories, setCategories] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState('');
  const [frontpage, setFrontpage] = useState(null);
  const [categoryArticles, setCategoryArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [crawling, setCrawling] = useState(false);
  const [undoState, setUndoState] = useState(null); // { articleId, title, verdict }
  const [formattedDate] = useState(() =>
    new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })
  );

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [catsRes, fpRes] = await Promise.all([
        getCategories(),
        getFrontpage(),
      ]);
      setCategories(catsRes);
      setFrontpage(fpRes);
    } catch (err) {
      console.error('Failed to load front page data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

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

  const handleSwipe = async (articleId, verdict) => {
    // Find article for undo toast message
    let articleTitle = 'Story';
    if (frontpage?.lead_story?.id === articleId) {
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
          const newSections = prev.sections.map((sec) => ({
            ...sec,
            articles: sec.articles.filter((a) => a.id !== articleId),
          })).filter((sec) => sec.articles.length > 0);
          return { lead_story: newLead, sections: newSections };
        });
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

  const handleOpenReader = (articleId) => {
    navigate(`/reader/${articleId}`);
  };

  const hasContent = selectedCategory
    ? categoryArticles.length > 0
    : Boolean(frontpage?.lead_story || frontpage?.sections?.length > 0);

  return (
    <div className="pb-16">
      {/* Editorial Masthead */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-brand-700 dark:text-volt-400">
            {formattedDate}
          </p>
          <h1 className="font-serif font-black text-3xl sm:text-4xl text-ink-950 dark:text-cream-50 tracking-tight mt-0.5">
            Today’s Edition
          </h1>
        </div>
        <button
          type="button"
          onClick={handleCrawlNow}
          disabled={crawling}
          className="flex items-center gap-2 self-start sm:self-auto bg-white dark:bg-ink-900 border border-cream-300 dark:border-ink-700 hover:bg-cream-100 dark:hover:bg-ink-800 text-xs font-semibold px-4 py-2 rounded-xl text-ink-800 dark:text-cream-100 shadow-xs transition-all"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-volt-500 ${crawling ? 'animate-spin' : ''}`} />
          <span>{crawling ? 'Updating feeds…' : 'Crawl now'}</span>
        </button>
      </div>

      {/* Sticky Category Bar */}
      <CategoryNav
        categories={categories}
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
                Swipe right to Keep • Left to Dismiss
              </span>
            </div>
            {categoryArticles.map((article) => (
              <ArticleRow
                key={article.id}
                article={article}
                onSwipe={handleSwipe}
                onOpenReader={handleOpenReader}
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
                onOpenReader={handleOpenReader}
              />
            )}

            {/* Categorized Sections */}
            {frontpage?.sections?.map((section) => (
              <CategorySection
                key={section.category.id}
                category={section.category}
                articles={section.articles}
                onSwipe={handleSwipe}
                onOpenReader={handleOpenReader}
                onSelectCategory={setSelectedCategory}
              />
            ))}
          </div>
        )}
      </div>

      {/* Undo Toast */}
      {undoState && (
        <UndoToast
          message={undoState.verdict === 'keep' ? 'Saved to Kept' : 'Dismissed story'}
          onUndo={handleUndo}
          onClose={() => setUndoState(null)}
        />
      )}
    </div>
  );
}
