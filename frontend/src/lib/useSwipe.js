import { useRef, useState } from 'react';

const DISTANCE = 60; // px before a drag counts as a swipe
const TAP = 10; // px a tap may wander

/**
 * Pointer swipes for the sail and quiz screens. Spread `handlers` on the element and
 * apply `style` to make it follow the finger sideways while dragging.
 */
export default function useSwipe({ onLeft, onRight, onUp, onDown, onTap }) {
  const start = useRef(null);
  const [dx, setDx] = useState(0);

  const end = (e) => {
    const s = start.current;
    start.current = null;
    setDx(0);
    if (!s) return;
    const x = e.clientX - s.x;
    const y = e.clientY - s.y;
    if (Math.abs(x) < TAP && Math.abs(y) < TAP) { onTap?.(e); return; }
    if (Math.abs(x) >= Math.abs(y)) {
      if (x <= -DISTANCE) onLeft?.();
      else if (x >= DISTANCE) onRight?.();
    } else if (y <= -DISTANCE) onUp?.();
    else if (y >= DISTANCE) onDown?.();
  };

  return {
    handlers: {
      onPointerDown: (e) => {
        if (e.button !== 0) return;
        start.current = { x: e.clientX, y: e.clientY };
        e.currentTarget.setPointerCapture?.(e.pointerId);
      },
      onPointerMove: (e) => {
        if (!start.current) return;
        const x = e.clientX - start.current.x;
        const y = e.clientY - start.current.y;
        setDx(Math.abs(x) > Math.abs(y) ? x : 0);
      },
      onPointerUp: end,
      onPointerCancel: () => { start.current = null; setDx(0); },
    },
    style: {
      transform: dx ? `translateX(${dx}px) rotate(${dx / 60}deg)` : undefined,
      transition: dx ? 'none' : 'transform 200ms ease-out',
    },
    dragging: dx !== 0,
  };
}
