import React from 'react';
import { RefreshCw } from 'lucide-react';

// Shows a way out instead of a blank screen when a page fails to draw (most
// often a page still running the app from before an update).
export default class ErrorBoundary extends React.Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error) {
    console.error('Dose page error:', error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="card card-pad max-w-md mx-auto my-16 text-center">
        <p className="font-display text-lg font-extrabold">This page didn't load.</p>
        <p className="mt-2 text-sm text-muted">
          Dose may have just been updated. Reloading picks up the latest version.
        </p>
        <button onClick={() => window.location.reload()} className="btn-primary mt-4">
          <RefreshCw className="w-4 h-4" aria-hidden="true" />
          <span>Reload</span>
        </button>
      </div>
    );
  }
}
