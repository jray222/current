# Current design system

Clean, editorial, and news-first. Paper-coloured pages, rich serif typography, structured sections, and fluid email-style gestures for triaging articles.
Tokens live in `frontend/tailwind.config.js` (scales) and `frontend/src/index.css` (neutral CSS variables and component classes). The architecture is shared with Staple, Glance, and Dose.

## Palette

Neutrals are CSS variables (space-separated RGB) so one class works in light and dark (`.dark` on `<html>`).

| Token | Light | Dark | Use |
|---|---|---|---|
| `cream` | 246 244 239 (`#F6F4EF`) | 17 20 21 | page background |
| `surface` | 255 255 255 | 29 33 34 | cards, sheets, inputs |
| `sunk` | 236 234 227 | 41 46 47 | wells in a card, chip backgrounds |
| `ink` | 26 33 33 | 238 241 238 | main text |
| `muted` | 96 106 104 | 160 170 167 | secondary text |
| `line` | 222 219 210 | 56 63 63 | borders, dividers |

Brand scales (fixed, 50-950):
- `brand` (ink blue, `#1F3A5F` anchor): primary branding, masthead, main buttons, headers.
- `volt` (electric yellow, `#F5C518` anchor): live crawl indicators, "Full article ready" badges, swipe Keep glow.
- `moss` (green): success states, verified checks.
- `amber`: warning badges, alerts.

Shadows are cool and soft: `shadow-soft`, `shadow-lift`, `shadow-pop`.

## Typography

- Headings and masthead: Fraunces Variable (`font-display`), an elegant serif with newspaper authority, weight 600.
- Body and UI: Nunito Sans Variable (`font-sans`), clean, readable, modern sans-serif.
- Inputs are 16px minimum so iOS Safari does not zoom on focus.

## Spacing and shape

- 4px grid via Tailwind; page gutter 16px on phones, 24px+ on desktop; cards pad 20px (`card-pad`).
- Radius: cards `rounded-3xl`, article thumbnails `rounded-xl`, buttons and chips rounded, inputs `rounded-2xl`.
- Touch targets at least 40px (`btn-icon` is 40x40).

## Components

| Component | Class / file | Notes |
|---|---|---|
| Card | `.card`, `.card-pad` | surface, soft shadow, hairline border |
| Button | `.btn-primary` `.btn-green` `.btn-soft` `.btn-ghost` `.btn-danger` `.btn-icon` | pill shaped, press scales to 97% |
| Chip | `.chip`, `.chip-on`, `.chip-moss`, `.chip-amber` | category filter pills; scroll horizontally on phones |
| Article Row | `components/news/ArticleRow.jsx` | email-style swipeable row (swipe right to Keep, swipe left to Skip) |
| Front Page | `pages/TodayPage.jsx` | digital newspaper layout: Top Stories + Category Sections |
| Reader | `pages/ReaderPage.jsx` | clean distraction-free reader column (65ch) with size & serif/sans toggles |
| Tab bar | `components/Shell.jsx` | bottom bar on phones (Today, Kept, Sources, More), side nav on desktop |

Motion is snappy (150-220ms) and disabled under `prefers-reduced-motion`.
