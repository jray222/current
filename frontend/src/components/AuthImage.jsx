import React, { useEffect, useRef, useState } from 'react';
import { fetchImageBlob } from '../api';

// Blob URLs by API path, so a picture is fetched once per session. Small LRU: the oldest are released.
const cache = new Map();
const inFlight = new Map();
const MAX_CACHED = 300;

function remember(path, url) {
  cache.set(path, url);
  if (cache.size > MAX_CACHED) {
    const oldest = cache.keys().next().value;
    URL.revokeObjectURL(cache.get(oldest));
    cache.delete(oldest);
  }
}

/** Fetches a picture into the cache (once), resolving to its blob URL. */
export function loadImage(path) {
  if (cache.has(path)) return Promise.resolve(cache.get(path));
  if (!inFlight.has(path)) {
    inFlight.set(path, fetchImageBlob(path).then((blob) => {
      const url = URL.createObjectURL(blob);
      remember(path, url);
      return url;
    }).finally(() => inFlight.delete(path)));
  }
  return inFlight.get(path);
}

/** Starts loading pictures that are about to be shown (the next cards while sailing). */
export function preloadImages(paths) {
  paths.filter(Boolean).forEach((p) => { loadImage(p).catch(() => {}); });
}

/** An <img> for a picture that needs the sign-in (collected photos).
 * Loads when scrolled near the screen. `path` is relative to the API root, e.g. /images/3/file.
 *  */
export default function AuthImage({ path, alt = '', className = '', imgClassName = 'w-full h-full object-cover', eager = false, onError, ...rest }) {
  const holder = useRef(null);
  const [src, setSrc] = useState(() => cache.get(path) || null);
  const [visible, setVisible] = useState(() => eager || cache.has(path));

  useEffect(() => {
    setSrc(cache.get(path) || null);
  }, [path]);

  useEffect(() => {
    if (visible || !holder.current) return undefined;
    if (typeof IntersectionObserver === 'undefined') { setVisible(true); return undefined; }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { setVisible(true); io.disconnect(); }
    }, { rootMargin: '300px' });
    io.observe(holder.current);
    return () => io.disconnect();
  }, [visible]);

  useEffect(() => {
    if (!visible || src) return undefined;
    let cancelled = false;
    loadImage(path).then((url) => {
      if (!cancelled) setSrc(url);
    }).catch(() => { if (!cancelled && onError) onError(); });
    return () => { cancelled = true; };
  }, [visible, src, path, onError]);

  return (
    <span ref={holder} className={`block ${className}`}>
      {src && <img src={src} alt={alt} className={imgClassName} draggable="false" {...rest} />}
    </span>
  );
}
