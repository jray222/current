import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import {
  setAccessToken as setApiAccessToken,
  setOnAuthExpired,
  getBootstrapStatus,
  register as apiRegister,
  login as apiLogin,
  verifyTwoFactor as apiVerifyTwoFactor,
  refreshSession,
  logout as apiLogout,
  getMe,
} from '../api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // Failed sign-ins to this account since its last visit, shown once after signing in.
  const [signInNotice, setSignInNotice] = useState(null);
  // Shown on the sign-in page after signing out on purpose (e.g. "You've left the household").
  const [signedOutNotice, setSignedOutNotice] = useState(null);
  const [initializing, setInitializing] = useState(true);
  const [bootstrap, setBootstrap] = useState({
    setup_required: false,
    registration_open: false,
    invite_only: false,
  });

  const clearSession = useCallback(() => {
    setApiAccessToken(null);
    setUser(null);
    setSignInNotice(null);
  }, []);

  useEffect(() => {
    setOnAuthExpired(() => clearSession());
  }, [clearSession]);

  // On first load: learn what sign-in options the server offers, then
  // silently try to resume a session via the httpOnly refresh cookie.
  useEffect(() => {
    (async () => {
      try {
        const status = await getBootstrapStatus();
        setBootstrap(status);
        // A reset link opens the "Set a new password" page, even in a browser that's signed in.
        if (status.setup_required || new URLSearchParams(window.location.search).has('reset')) return;
        try {
          const { access_token } = await refreshSession();
          setApiAccessToken(access_token);
          setUser(await getMe());
        } catch {
          clearSession();
        }
      } catch (err) {
        console.error('Failed to determine auth status:', err);
      } finally {
        setInitializing(false);
      }
    })();
  }, [clearSession]);

  const startSession = (result) => {
    setApiAccessToken(result.access_token);
    setUser(result.user);
    setSignInNotice(result.failed_attempts || null);
    setBootstrap((b) => ({ ...b, setup_required: false }));
  };

  const login = async (username, password) => {
    const result = await apiLogin(username, password);
    if (result.mfa_required) {
      return { mfaRequired: true, mfaToken: result.mfa_token };
    }
    startSession(result);
    return { mfaRequired: false };
  };

  const verifyTwoFactor = async (mfaToken, code) => {
    startSession(await apiVerifyTwoFactor(mfaToken, code));
  };

  const register = async (details) => {
    startSession(await apiRegister(details));
  };

  const logout = async () => {
    try {
      await apiLogout();
    } catch {
      // ignore network errors on logout, clear client state regardless
    }
    clearSession();
  };

  // The account is gone (left the household): back to the sign-in page with a note.
  const endSession = (notice) => {
    clearSession();
    setSignedOutNotice(notice || null);
  };

  const refreshUser = async () => {
    const me = await getMe();
    setUser(me);
    return me;
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        initializing,
        setupRequired: bootstrap.setup_required,
        registrationOpen: bootstrap.registration_open,
        inviteOnly: bootstrap.invite_only,
        login,
        verifyTwoFactor,
        register,
        logout,
        endSession,
        signedOutNotice,
        refreshUser,
        signInNotice,
        dismissSignInNotice: () => setSignInNotice(null),
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
