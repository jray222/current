import React from 'react';
import {
  Atom, Bird, BookOpen, Bug, Drama, Fish, Flower2, Globe, Landmark, Layers, Leaf, Mountain, Orbit, Palette,
  PawPrint, Trees, Music, FlaskConical, Shell,
} from 'lucide-react';

// The icon names a pack may use (Claude picks from these too).
const ICONS = {
  atom: Atom, bird: Bird, 'book-open': BookOpen, bug: Bug, drama: Drama, fish: Fish, 'flower-2': Flower2,
  flower: Flower2, globe: Globe, landmark: Landmark, leaf: Leaf, mountain: Mountain, orbit: Orbit,
  palette: Palette, 'paw-print': PawPrint, trees: Trees, tree: Trees, music: Music, flask: FlaskConical,
  'flask-conical': FlaskConical, shell: Shell,
};

export default function DeckIcon({ name, className = 'w-5 h-5' }) {
  const Icon = ICONS[name] || Layers;
  return <Icon className={className} aria-hidden="true" />;
}
