# Current Design System

Current is a personal news site and reader designed around an editorial newspaper aesthetic with fluid, tactile mobile email-style gestures.

---

## 1. Typography

Current pairs an editorial serif headline font with a high-legibility sans-serif for UI and body text:

- **Display & Headlines (`font-serif`)**: [Fraunces](https://fonts.google.com/specimen/Fraunces)
  - Used for the brand masthead, Top Story headlines, category section headers, and article reader titles.
  - Optical sizes and soft letterforms evoke classic broadsheets and literary magazines.
- **Body & UI (`font-sans`)**: [Nunito Sans](https://fonts.google.com/specimen/Nunito+Sans)
  - Used for navigation, metadata pills, article summaries, swipe labels, and forms.
  - Generous x-height ensures readability across mobile and desktop displays.
- **Reading Content (`prose prose-slate`)**:
  - Distraction-free reader view enforces line lengths between 60–75 characters (`max-w-2xl`).
  - Font sizes scale cleanly: `text-lg` with `leading-relaxed` (1.75 line height).

---

## 2. Color Palette & Identity

Current's identity combines classic print neutrality with an energetic "volt" accent:

| Token | Hex / Value | Usage |
|---|---|---|
| **Background (Light)** | `#f8fafc` (`slate-50`) | Main canvas and newspaper background |
| **Surface (Light)** | `#ffffff` (`white`) | Article cards, rows, reading modal |
| **Border (Light)** | `#e2e8f0` (`slate-200`) | Editorial section dividing rules |
| **Text Primary** | `#0f172a` (`slate-900`) | Headlines, article text |
| **Text Muted** | `#64748b` (`slate-500`) | Timestamps, source bylines, reading time |
| **Accent / Volt** | `#f59e0b` (`amber-500`) | Zigzag lightning bolt, active category pill |
| **Keep / Save Action** | `#16a34a` (`emerald-600`) | Right swipe reveal background, bookmark badge |
| **Skip / Dismiss Action** | `#475569` (`slate-600`) | Left swipe reveal background, dismiss trash icon |
| **Background (Dark)** | `#0f172a` (`slate-900`) | Dark mode canvas |
| **Surface (Dark)** | `#1e293b` (`slate-800`) | Dark mode cards and rows |

---

## 3. Editorial Front Page Hierarchy

The Today view mirrors modern digital newsrooms:

1. **Sticky Category Bar (`CategoryNav`)**:
   - Horizontal pill bar with unread counts and icons (Flame for Top stories, Globe for World, Landmark for Politics, CPU for Tech, etc.).
   - Quick jump to section or filter to single category feed.
2. **Top Stories Hero (`LeadStoryCard`)**:
   - The #1 highest-ranked story in the user's edition is elevated to a full-bleed lead hero card.
   - Large image thumbnail, bold serif headline, publication source badge, and swipe/button actions.
3. **Category Sections (`CategorySection`)**:
   - Grouped articles divided by category headers with unread count chips.
   - First article in each section features a medium horizontal card; subsequent stories render as compact swipe rows.
4. **Story Clustering Indicators**:
   - Clustered stories across multiple outlets display an "Also in: [Other Source]" indicator. Swiping an article handles the entire clustered story.

---

## 4. Email-Style Swipe Interaction (`useSwipeRow`)

Articles in the feed use a tactile, mobile email-style horizontal swipe gesture:

- **Threshold**: 35% of row width or 120px minimum drag.
- **Right Swipe (> +35%)**:
  - Reveals Emerald background (`bg-emerald-600`) with Bookmark icon + "Keep".
  - Full-swipe continuous release immediately saves to the Kept reading list.
- **Left Swipe (< -35%)**:
  - Reveals Slate background (`bg-slate-600`) with Trash icon + "Dismiss".
  - Full-swipe continuous release skips the story and collapses the row.
- **Continuous Release Animation**:
  - Once released past the threshold, the row animates out smoothly (`transform: translateX(...)`).
  - Height transitions to 0 (`max-height: 0; opacity: 0; margin: 0; padding: 0;`) over 250ms with `cubic-bezier(0.4, 0, 0.2, 1)`.
- **Undo Toast (`UndoToast`)**:
  - Appears at the bottom of the screen with a 5-second countdown progress bar.
  - Tapping "Undo" immediately restores the article row and reverts the interest model's weights.

---

## 5. Distraction-Free Reader View

- Full-screen or modal reader (`/reader/:id`).
- Strictly renders sanitized plain-text blocks (`p`, `h2`, `h3`, `quote`, `li`, `pre`).
- Direct links to original publisher with `ExternalLink` icon and `rel="noopener noreferrer"`.
- Text extraction status indicator (`TextStatus`):
  - Shows reading time, word count, and method (`http`, `amp`, or `browser`).
  - Clear notice if paywalled or partial, with a 1-tap "Fetch full text" button.
- Bottom floating bar with quick Keep, Share, and Close controls.

---

## 6. Accessibility & Responsiveness

- All interactive buttons have explicit `aria-label` tags.
- Full desktop keyboard support (arrow navigation, click-to-open, keyboard shortcuts `k` to keep, `s` to skip).
- Responsive layouts adapt from 390px mobile screens (touch swiping, single column) to 1200px+ widescreen displays (multi-column editorial grid).
