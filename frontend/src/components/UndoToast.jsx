import React, { useEffect } from 'react';
import { Undo2, X } from 'lucide-react';

export default function UndoToast({ message, onUndo, onClose, duration = 5000 }) {
  useEffect(() => {
    if (!message) return undefined;
    const timer = setTimeout(() => {
      if (onClose) onClose();
    }, duration);
    return () => clearTimeout(timer);
  }, [message, duration, onClose]);

  if (!message) return null;

  return (
    <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-ink-900 text-white px-4 py-2.5 rounded-full shadow-lg border border-ink-700 animate-slide-up text-sm font-medium">
      <span>{message}</span>
      {onUndo && (
        <button
          onClick={onUndo}
          className="flex items-center gap-1 text-volt-400 hover:text-volt-300 font-semibold px-2 py-0.5 rounded transition-colors"
        >
          <Undo2 className="w-3.5 h-3.5" />
          Undo
        </button>
      )}
      <button
        onClick={onClose}
        className="text-ink-400 hover:text-ink-200 p-0.5 rounded transition-colors"
        aria-label="Dismiss"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
