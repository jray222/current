import { useState, useRef, useCallback } from 'react';

/**
 * Hook for iOS/mobile email-style horizontal swiping on individual article rows.
 * Supports continuous release threshold (>35% right = keep, <-35% left = skip).
 */
export function useSwipeRow({ onSwipeRight, onSwipeLeft, onTap, threshold = 0.35 }) {
  const [offsetX, setOffsetX] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [isCollapsing, setIsCollapsing] = useState(false);
  const [swipeAction, setSwipeAction] = useState(null); // 'keep' | 'skip' | null

  const touchStart = useRef({ x: 0, y: 0, time: 0 });
  const rowRef = useRef(null);
  const isHorizontal = useRef(null);

  const handleTouchStart = useCallback((e) => {
    if (isCollapsing) return;
    const touch = e.touches ? e.touches[0] : e;
    touchStart.current = { x: touch.clientX, y: touch.clientY, time: Date.now() };
    isHorizontal.current = null;
    setIsDragging(true);
  }, [isCollapsing]);

  const handleTouchMove = useCallback((e) => {
    if (!isDragging || isCollapsing) return;
    const touch = e.touches ? e.touches[0] : e;
    const deltaX = touch.clientX - touchStart.current.x;
    const deltaY = touch.clientY - touchStart.current.y;

    // Determine swipe direction intent on first significant movement
    if (isHorizontal.current === null) {
      if (Math.abs(deltaY) > Math.abs(deltaX) && Math.abs(deltaY) > 5) {
        isHorizontal.current = false; // vertical scroll, don't swipe
        setIsDragging(false);
        setOffsetX(0);
        return;
      }
      if (Math.abs(deltaX) > 5) {
        isHorizontal.current = true;
      }
    }

    if (!isHorizontal.current) return;

    if (e.cancelable && e.preventDefault) {
      e.preventDefault();
    }

    const width = rowRef.current?.offsetWidth || 300;
    // Add elastic resistance past threshold
    let targetX = deltaX;
    if (Math.abs(deltaX) > width * 0.6) {
      const excess = Math.abs(deltaX) - width * 0.6;
      targetX = (deltaX > 0 ? 1 : -1) * (width * 0.6 + excess * 0.3);
    }

    setOffsetX(targetX);

    const ratio = deltaX / width;
    if (ratio > threshold) {
      setSwipeAction('keep');
    } else if (ratio < -threshold) {
      setSwipeAction('skip');
    } else {
      setSwipeAction(null);
    }
  }, [isDragging, isCollapsing, threshold]);

  const handleTouchEnd = useCallback(() => {
    if (!isDragging) return;
    setIsDragging(false);

    const width = rowRef.current?.offsetWidth || 300;
    const ratio = offsetX / width;
    const elapsed = Date.now() - touchStart.current.time;

    // Detect tap: small movement and short time
    if (Math.abs(offsetX) < 8 && elapsed < 350) {
      setOffsetX(0);
      setSwipeAction(null);
      if (onTap) onTap();
      return;
    }

    // Trigger full swipe action if passed threshold
    if (ratio > threshold) {
      // Swiped right -> Keep
      setOffsetX(width + 50);
      setIsCollapsing(true);
      setTimeout(() => {
        if (onSwipeRight) onSwipeRight();
      }, 250);
    } else if (ratio < -threshold) {
      // Swiped left -> Skip
      setOffsetX(-width - 50);
      setIsCollapsing(true);
      setTimeout(() => {
        if (onSwipeLeft) onSwipeLeft();
      }, 250);
    } else {
      // Snap back
      setOffsetX(0);
      setSwipeAction(null);
    }
  }, [isDragging, offsetX, threshold, onSwipeRight, onSwipeLeft, onTap]);

  return {
    rowRef,
    offsetX,
    isDragging,
    isCollapsing,
    swipeAction,
    handlers: {
      onTouchStart: handleTouchStart,
      onTouchMove: handleTouchMove,
      onTouchEnd: handleTouchEnd,
      onMouseDown: handleTouchStart,
      onMouseMove: handleTouchMove,
      onMouseUp: handleTouchEnd,
      onMouseLeave: handleTouchEnd,
    },
  };
}
