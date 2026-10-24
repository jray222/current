import { useEffect, useRef } from 'react';

/** Calls `reload` every few seconds while `active` (a deck is gathering pictures). */
export default function useDeckPolling(active, reload, everyMs = 4000) {
  const saved = useRef(reload);
  saved.current = reload;
  useEffect(() => {
    if (!active) return undefined;
    const id = setInterval(() => saved.current(), everyMs);
    return () => clearInterval(id);
  }, [active, everyMs]);
}
