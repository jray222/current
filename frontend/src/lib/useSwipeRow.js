import { useState, useRef, useCallback, useEffect } from 'react';

/**
 * Hook for iOS/mobile email-style horizontal swiping and long-press actions on individual article rows.
 * Supports continuous release threshold (>35% right = keep, <-35% left = skip) and long-press (>480ms).
 */
export function useSwipeRow({
  onSwipeRight,
  onSwipeLeft,
  onTap,
  onLongPress,
  threshold = 0.35,
  longPressMs = 480,
}) {
  const [offsetX, setOffsetX] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [isCollapsing, setIsCollapsing] = useState(false);
  const [swipeAction, setSwipeAction] = useState(null); // 'keep' | 'skip' | null

  const touchStart = useRef({ x: 0, y: 0, time: 0 });
  const rowRef = useRef(null);
  const isHorizontal = useRef(null);
  const longPressTimer = useRef(null);
  const longPressTriggered = useRef(false);
  const lastTouchTime = useRef(0);

  const clearLongPress = useCallback(() => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  }, []);

  useEffect(() => () => clearLongPress(), [clearLongPress]);

  const startGesture = useCallback(
    (clientX, clientY) => {
      if (isCollapsing) return;
      touchStart.current = { x: clientX, y: clientY, time: Date.now() };
      isHorizontal.current = null;
      longPressTriggered.current = false;
      setIsDragging(true);

      clearLongPress();
      if (onLongPress) {
        longPressTimer.current = setTimeout(() => {
          longPressTimer.current = null;
          longPressTriggered.current = true;
          setIsDragging(false);
          setOffsetX(0);
          setSwipeAction(null);
          try {
            navigator.vibrate?.(15);
          } catch {
            // ignore unsupported vibration API
          }
          onLongPress();
        }, longPressMs);
      }
    },
    [isCollapsing, clearLongPress, onLongPress, longPressMs]
  );

  const handleTouchStart = useCallback(
    (e) => {
      lastTouchTime.current = Date.now();
      const touch = e.touches[0];
      if (!touch) return;
      startGesture(touch.clientX, touch.clientY);
    },
    [startGesture]
  );

  const handleMouseDown = useCallback(
    (e) => {
      if (e.button !== 0) return;
      if (Date.now() - lastTouchTime.current < 700) return;
      startGesture(e.clientX, e.clientY);
    },
    [startGesture]
  );

  const handleMove = useCallback(
    (e) => {
      if (!isDragging || isCollapsing || longPressTriggered.current) return;
      const touch = e.touches ? e.touches[0] : e;
      if (!touch) return;
      const deltaX = touch.clientX - touchStart.current.x;
      const deltaY = touch.clientY - touchStart.current.y;

      if (Math.abs(deltaX) > 8 || Math.abs(deltaY) > 8) {
        clearLongPress();
      }

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
    },
    [isDragging, isCollapsing, threshold, clearLongPress]
  );

  const handleEnd = useCallback(() => {
    clearLongPress();
    if (longPressTriggered.current) {
      longPressTriggered.current = false;
      setIsDragging(false);
      setOffsetX(0);
      setSwipeAction(null);
      return;
    }
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
  }, [isDragging, offsetX, threshold, onSwipeRight, onSwipeLeft, onTap, clearLongPress]);

  const handleTouchEnd = useCallback(() => {
    lastTouchTime.current = Date.now();
    handleEnd();
  }, [handleEnd]);

  const handleCancel = useCallback(() => {
    clearLongPress();
    longPressTriggered.current = false;
    setIsDragging(false);
    setOffsetX(0);
    setSwipeAction(null);
  }, [clearLongPress]);

  const handleContextMenu = useCallback(
    (e) => {
      if (!onLongPress) return;
      e.preventDefault();
      clearLongPress();
      setIsDragging(false);
      setOffsetX(0);
      setSwipeAction(null);
      if (!longPressTriggered.current) {
        onLongPress();
      }
      longPressTriggered.current = false;
    },
    [onLongPress, clearLongPress]
  );

  return {
    rowRef,
    offsetX,
    isDragging,
    isCollapsing,
    swipeAction,
    handlers: {
      onTouchStart: handleTouchStart,
      onTouchMove: handleMove,
      onTouchEnd: handleTouchEnd,
      onTouchCancel: handleCancel,
      onMouseDown: handleMouseDown,
      onMouseMove: handleMove,
      onMouseUp: handleEnd,
      onMouseLeave: handleCancel,
      onContextMenu: handleContextMenu,
    },
  };
}
