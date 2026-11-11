/** Current design tokens. See docs/DESIGN_SYSTEM.md.
 *
 * Neutral surfaces (page, card, text, borders) are CSS variables set in src/index.css,
 * so one class (bg-cream, text-ink...) works in both light and dark mode. The brand
 * colours (ink blue, volt yellow, moss green, amber) are fixed scales. */
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        cream: token('cream'),       // page background (#F6F4EF in light mode)
        surface: token('surface'),   // cards, sheets, inputs
        sunk: token('sunk'),         // wells inside a card, chip backgrounds
        ink: token('ink'),           // main text
        muted: token('muted'),       // secondary text
        line: token('line'),         // borders and dividers
        brand: {
          50: '#f0f4f9', 100: '#dbe5f1', 200: '#b9cde3', 300: '#8faed1', 400: '#5f8bbc',
          500: '#3c6da4', 600: '#2c5586', 700: '#1F3A5F', 800: '#192e4c', 900: '#14253c', 950: '#0d1726',
        },
        volt: {
          50: '#fffde7', 100: '#fff9c4', 200: '#fff176', 300: '#ffea00', 400: '#ffd600',
          500: '#F5C518', 600: '#e0ad08', 700: '#b88a04', 800: '#8f6a02', 900: '#664a02',
        },
        moss: {
          50: '#f1f8ec', 100: '#deefd2', 200: '#bfdfa8', 300: '#9acb77', 400: '#78b54f',
          500: '#5c9a36', 600: '#477b28', 700: '#385f22', 800: '#2f4c1f', 900: '#24391a',
        },
        amber: {
          50: '#fff8eb', 100: '#feecc7', 200: '#fdd88a', 300: '#fcc04d', 400: '#fbab24',
          500: '#f08c0b', 600: '#d46a06', 700: '#b04a09',
        },
        berry: { 100: '#fde4ee', 500: '#e0568a', 700: '#a82d5d' },
        sky: { 100: '#dff1fb', 500: '#3b9fd8', 700: '#1f6f9f' },
      },
      fontFamily: {
        display: ['"Fraunces Variable"', 'Georgia', 'ui-serif', 'serif'],
        sans: ['"Nunito Sans Variable"', 'system-ui', '-apple-system', '"Segoe UI"', 'Roboto', 'sans-serif'],
      },
      borderRadius: {
        '4xl': '2rem',
      },
      boxShadow: {
        // Soft, cool, never pure black.
        soft: '0 1px 2px rgb(20 35 55 / 0.06), 0 4px 14px rgb(20 35 55 / 0.08)',
        lift: '0 2px 4px rgb(20 35 55 / 0.08), 0 12px 28px rgb(20 35 55 / 0.14)',
        pop: '0 6px 18px rgb(31 58 95 / 0.35)',
      },
    },
  },
  plugins: [],
}
