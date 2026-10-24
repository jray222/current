# Dose design system

Calm and photo-first. Paper-coloured pages and soft cards for browsing; a black, full-screen stage for sailing and quizzing, where the photo is the point.
Tokens live in `frontend/tailwind.config.js` (scales) and `frontend/src/index.css` (neutral CSS variables and component classes). The structure is shared with Staple and Glance.

## Palette

Neutrals are CSS variables (space-separated RGB) so one class works in light and dark (`.dark` on `<html>`).

| Token | Light | Dark | Use |
|---|---|---|---|
| `cream` | 246 244 239 | 17 20 21 | page background |
| `surface` | 255 255 255 | 29 33 34 | cards, sheets, inputs |
| `sunk` | 236 234 227 | 41 46 47 | wells in a card, chip backgrounds |
| `ink` | 26 33 33 | 238 241 238 | main text |
| `muted` | 96 106 104 | 160 170 167 | secondary text |
| `line` | 222 219 210 | 56 63 63 | borders, dividers |

Brand scales (fixed, 50-900): `brand` teal (primary actions, 600 is the button; seen cards), `moss` (known, success),
`amber` (owner tools, warnings), plus `berry` and `sky` accents.
Shadows are cool and soft: `shadow-soft`, `shadow-lift`, `shadow-pop` (primary button glow).

## Type

- Headings and card names: Fraunces Variable (`font-display`), a soft serif with an encyclopedia feel, weight 600.
- Body: Nunito Sans Variable (`font-sans`).
- Inputs are 16px minimum so iOS does not zoom on focus.

## Spacing and shape

- 4px grid via Tailwind; page gutter 16px on phones, 24px+ on desktop; cards pad 20px (`card-pad`).
- Radius: cards `rounded-3xl`, card photos `rounded-2xl`, buttons and chips fully round, inputs `rounded-2xl`.
- Touch targets at least 40px (`btn-icon` is 40x40).

## Components

| Component | Class / file | Notes |
|---|---|---|
| Card | `.card`, `.card-pad` | surface, soft shadow, hairline border |
| Button | `.btn-primary` `.btn-green` `.btn-soft` `.btn-ghost` `.btn-danger` `.btn-icon` | pill shaped, press scales to 97% |
| Chip | `.chip`, `.chip-on`, `.chip-moss`, `.chip-amber` | filter pills; rows scroll horizontally on phones |
| Input | `.input` | rounded, teal focus ring |
| Modal | `components/Modal.jsx` | bottom sheet on phones, centred dialog from `sm` up |
| Tab bar | `components/Shell.jsx` | bottom bar on phones (Today, Decks, More), side nav on desktop |
| Deck bits | `components/deck/` | cover, progress bar (known moss, seen teal), collecting status, icon, picture chooser |
| Stage | `pages/SailPage.jsx`, `pages/QuizPage.jsx` | black, full screen, no nav; blurred copy of the photo fills behind the whole photo; text on a bottom gradient |

Photos always show their credit (author, licence, source link) on the stage.
Motion is short (150-220ms) and disabled under `prefers-reduced-motion`; the auto-advance bar becomes static.
