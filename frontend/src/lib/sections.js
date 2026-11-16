import { Newspaper, Cpu, Car, ShoppingBag, Layers } from 'lucide-react';

export const SOURCE_SECTIONS = [
  { key: 'news', label: 'News', icon: Newspaper },
  { key: 'tech', label: 'Tech', icon: Cpu },
  { key: 'cars', label: 'Cars', icon: Car },
  { key: 'shopping', label: 'Shopping', icon: ShoppingBag },
];

export const ALL_SECTIONS_TAB = {
  key: '',
  label: 'All',
  icon: Layers,
};

export const SOURCE_SECTION_MAP = Object.fromEntries(
  SOURCE_SECTIONS.map((s) => [s.key, s])
);

export function getSectionMeta(key) {
  return SOURCE_SECTION_MAP[key] || SOURCE_SECTION_MAP.news;
}
