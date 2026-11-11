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
    <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-brand-950 text-white px-5 py-2.5 rounded-full shadow-2xl border border-brand-800 text-sm font-semibold tracking-wide">
      <span>{message}</span>
      {onUndo && (
        <button
          onClick={onUndo}
          className="flex items-center gap-1.5 text-volt-400 hover:text-volt-300 font-bold px-2 py-0.5 rounded-md hover:bg-white/10 transition-colors"
        >
          <Undo2 className="w-3.5 h-3.5" />
          Undo
        </button>
      )}
      <button
        onClick={onClose}
        className="text-white/60 hover:text-white p-0.5 rounded-full transition-colors"
        aria-label="Dismiss"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
