import React, { useEffect, useState } from 'react';
import { Lock, User, KeyRound, Loader2, Home, Ticket, CheckCircle2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { checkInvite, checkResetLink, resetPassword } from '../api';
import { Logo } from './Brand';
import { ErrorBanner, errorOf } from './ui';

// Invite links look like https://dose.example.com/?invite=K7QX-M2HD-9TRA
const inviteFromUrl = () => new URLSearchParams(window.location.search).get('invite') || '';

// Reset links look like https://dose.example.com/?reset=<token>
const resetFromUrl = () => new URLSearchParams(window.location.search).get('reset') || '';

const forgetParamInUrl = (name) => {
  const url = new URL(window.location.href);
  if (url.searchParams.has(name)) {
    url.searchParams.delete(name);
    window.history.replaceState(null, '', url.pathname + url.search + url.hash);
  }
};

const PASSWORD_HINT =
  'At least 12 characters, with uppercase, lowercase, a number, and a special character.';

function AuthShell({ children }) {
  return (
    <div className="min-h-screen bg-cream flex items-center justify-center p-4 relative overflow-hidden">
      {/* Soft decorative blobs */}
      <div className="absolute -top-24 -left-24 w-72 h-72 rounded-full bg-amber-200/60 dark:bg-amber-600/10 blur-2xl" aria-hidden="true" />
      <div className="absolute -bottom-28 -right-20 w-80 h-80 rounded-full bg-brand-200/60 dark:bg-brand-700/15 blur-2xl" aria-hidden="true" />
      <div className="absolute top-1/3 -right-16 w-52 h-52 rounded-full bg-moss-200/60 dark:bg-moss-700/15 blur-2xl" aria-hidden="true" />
      <div className="w-full max-w-md relative">
        <div className="flex flex-col items-center mb-7 space-y-3">
          <Logo className="w-16 h-16 drop-shadow-md" />
          <div className="text-center">
            <h1 className="text-4xl text-ink">Dose</h1>
            <p className="text-muted font-semibold">Pick the week. Shop once. Eat well.</p>
          </div>
        </div>
        <div className="card card-pad space-y-5 shadow-lift">
          {children}
        </div>
      </div>
    </div>
  );
}

function IconInput({ icon: Icon, className = '', ...props }) {
  return (
    <div className="relative">
      <Icon className="w-4 h-4 text-muted absolute left-4 top-1/2 -translate-y-1/2" aria-hidden="true" />
      <input {...props} className={`input pl-10 ${className}`} />
    </div>
  );
}

function SubmitButton({ busy, children }) {
  return (
    <button type="submit" disabled={busy} className="btn-primary w-full py-3 text-base">
      {busy && <Loader2 className="w-4 h-4 animate-spin" />}
      <span>{children}</span>
    </button>
  );
}

function InviteField({ code, setCode, invite }) {
  return (
    <div>
      <label className="label" htmlFor="invite-code">Invite code</label>
      <IconInput
        icon={Ticket}
        id="invite-code"
        required
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder="XXXX-XXXX-XXXX"
        autoComplete="off"
        className="font-mono tracking-widest uppercase"
      />
      {invite?.valid === false && code.trim() && (
        <p className="text-xs text-brand-700 dark:text-brand-300 mt-1.5">This invite is invalid, used up or expired. Ask for a new one.</p>
      )}
    </div>
  );
}

function RegisterForm({ needsInvite, initialCode = '' }) {
  const { register, setupRequired } = useAuth();
  const [username, setUsername] = useState('');
  const [householdName, setHouseholdName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [inviteCode, setInviteCode] = useState(initialCode);
  const [invite, setInvite] = useState(null); // what the code is for, once checked
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Look the code up as it's typed / arrives from the link, so the form can say what it's for.
  useEffect(() => {
    const code = inviteCode.replace(/[^A-Za-z0-9]/g, '');
    if (code.length < 12) { setInvite(null); return undefined; }
    let cancelled = false;
    const t = setTimeout(() => {
      checkInvite(inviteCode).then((res) => { if (!cancelled) setInvite(res); }).catch(() => {});
    }, 250);
    return () => { cancelled = true; clearTimeout(t); };
  }, [inviteCode]);

  const joining = invite?.valid && invite.kind === 'member';

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    try {
      setSubmitting(true);
      await register({
        username,
        password,
        email: email || undefined,
        householdName: (!joining && householdName) || undefined,
        inviteCode: inviteCode.trim() || undefined,
      });
      forgetParamInUrl('invite');
    } catch (err) {
      setError(errorOf(err, 'Could not create your account.'));
    } finally {
      setSubmitting(false);
    }
  };

  let subtitle = 'This creates a new private household. You can invite family members and turn on two-factor authentication after signing in.';
  if (setupRequired) subtitle = 'You are the first user, so you will also own this instance and manage its settings.';
  else if (needsInvite && !invite?.valid) subtitle = 'Sign-up here is by invitation. Enter the code from your invite link.';

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <h2 className="text-2xl">
          {setupRequired ? 'Set up Dose' : joining ? `Join ${invite.household_name}` : 'Create your account'}
        </h2>
        <p className="text-sm text-muted mt-1">{joining ? 'You will learn from the same decks as everyone here.' : subtitle}</p>
      </div>

      {invite?.valid && (
        <div className="banner-ok">
          <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
          <span>
            {joining
              ? <>You've been invited to join <strong>{invite.household_name}</strong>.</>
              : 'You\'ve been invited to Dose.'}
          </span>
        </div>
      )}

      <ErrorBanner message={error} />

      {(needsInvite || initialCode) && !setupRequired && (
        <InviteField code={inviteCode} setCode={setInviteCode} invite={invite} />
      )}

      <div>
        <label className="label" htmlFor="reg-username">Username</label>
        <IconInput icon={User} id="reg-username" required autoFocus value={username} autoComplete="username"
          onChange={(e) => setUsername(e.target.value)} placeholder="e.g. jsmith" />
      </div>

      {!joining && (
        <div>
          <label className="label" htmlFor="reg-household">Household name (optional)</label>
          <IconInput icon={Home} id="reg-household" value={householdName} maxLength={100}
            onChange={(e) => setHouseholdName(e.target.value)} placeholder="e.g. The Smith Family" />
        </div>
      )}

      <div>
        <label className="label" htmlFor="reg-email">Email (optional)</label>
        <input id="reg-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com" className="input" />
      </div>

      <div>
        <label className="label" htmlFor="reg-password">Password</label>
        <IconInput icon={Lock} id="reg-password" required type="password" value={password} autoComplete="new-password"
          onChange={(e) => setPassword(e.target.value)} />
        <p className="text-xs text-muted mt-1.5">{PASSWORD_HINT}</p>
      </div>

      <div>
        <label className="label" htmlFor="reg-confirm">Confirm password</label>
        <input id="reg-confirm" required type="password" value={confirmPassword} autoComplete="new-password"
          onChange={(e) => setConfirmPassword(e.target.value)} className="input" />
      </div>

      <SubmitButton busy={submitting}>{submitting ? 'Creating account...' : 'Create account'}</SubmitButton>
    </form>
  );
}

/** "Set a new password" from a one-time reset link made by a household admin (or the instance owner). */
function ResetPasswordForm({ token, onDone }) {
  const [link, setLink] = useState(null); // { valid, username, expires_at }
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    checkResetLink(token).then(setLink).catch(() => setLink({ valid: false }));
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    if (password !== confirmPassword) { setError('Passwords do not match.'); return; }
    try {
      setSubmitting(true);
      const res = await resetPassword(token, password);
      forgetParamInUrl('reset');
      onDone(res.username);
    } catch (err) {
      setError(errorOf(err, 'Could not set the password.'));
    } finally {
      setSubmitting(false);
    }
  };

  const leave = () => { forgetParamInUrl('reset'); onDone(null); };

  if (!link) return <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 animate-spin text-muted" /></div>;
  if (!link.valid) {
    return (
      <div className="space-y-4" data-testid="reset-invalid">
        <h2 className="text-2xl">This reset link doesn&apos;t work</h2>
        <p className="text-muted">
          It was already used, it&apos;s more than an hour old, or a newer one replaced it. Ask whoever sent it for a new one.
        </p>
        <button type="button" onClick={leave} className="btn-soft">&larr; Back to sign in</button>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="space-y-4" data-testid="reset-form">
      <div>
        <h2 className="text-2xl">Set a new password</h2>
        <p className="text-sm text-muted mt-1">
          For <strong className="text-ink">{link.username}</strong>. Every device signed in to this account will be
          signed out. Two-step verification, if it&apos;s on, stays on.
        </p>
      </div>
      <ErrorBanner message={error} />
      <div>
        <label htmlFor="reset-password" className="label">New password</label>
        <IconInput icon={Lock} id="reset-password" required autoFocus type="password" value={password}
          autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} />
        <p className="text-xs text-muted mt-1.5">{PASSWORD_HINT}</p>
      </div>
      <div>
        <label htmlFor="reset-confirm" className="label">Type it again</label>
        <input id="reset-confirm" required type="password" value={confirmPassword} autoComplete="new-password"
          onChange={(e) => setConfirmPassword(e.target.value)} className="input" />
      </div>
      <SubmitButton busy={submitting}>{submitting ? 'Saving...' : 'Set new password'}</SubmitButton>
    </form>
  );
}

/** No email: a household admin makes a reset link, and the instance owner uses the server command. */
function ForgotPassword() {
  const [open, setOpen] = useState(false);
  return (
    <div className="text-sm text-muted">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className="font-semibold hover:text-ink underline underline-offset-2 cursor-pointer">
        Forgot your password?
      </button>
      {open && (
        <p className="mt-2" data-testid="forgot-help">
          Ask an admin of your household for a reset link (Settings &rarr; Household). Admins can ask whoever runs this
          Dose. If that&apos;s you, run <code className="text-ink">python -m app.cli reset-password &lt;username&gt;</code> in
          the container.
        </p>
      )}
    </div>
  );
}

// The same for every refusal, so it says nothing about whether the account exists or is paused.
function PauseHint({ failures }) {
  if (failures < 2) return null;
  return (
    <p className="text-xs text-muted" data-testid="pause-hint">
      Sure it's right? After 5 wrong tries, Dose pauses sign-in from new devices for 15 minutes or longer. Devices
      you've signed in on before aren't affected, and a household admin can lift the pause.
    </p>
  );
}

function LoginForm({ notice }) {
  const { login, verifyTwoFactor } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [mfaToken, setMfaToken] = useState(null);
  const [error, setError] = useState(null);
  const [failures, setFailures] = useState(0);
  const [submitting, setSubmitting] = useState(false);

  const handlePasswordSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      setSubmitting(true);
      const result = await login(username, password);
      if (result.mfaRequired) {
        setMfaToken(result.mfaToken);
      }
    } catch (err) {
      setError(errorOf(err, 'Login failed. Please try again.'));
      if (err.response?.status === 401) setFailures((n) => n + 1);
    } finally {
      setSubmitting(false);
    }
  };

  const handleMfaSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      setSubmitting(true);
      await verifyTwoFactor(mfaToken, code);
    } catch (err) {
      setError(errorOf(err, 'Invalid authentication code.'));
      if (err.response?.status === 401) setFailures((n) => n + 1);
    } finally {
      setSubmitting(false);
    }
  };

  if (mfaToken) {
    return (
      <form onSubmit={handleMfaSubmit} className="space-y-4">
        <div>
          <h2 className="text-2xl">Two-factor check</h2>
          <p className="text-sm text-muted mt-1">
            Enter the 6-digit code from your authenticator app, or one of your backup codes.
          </p>
        </div>

        <ErrorBanner message={error} />
        <PauseHint failures={failures} />

        <div>
          <label className="label" htmlFor="mfa-code">Authentication code</label>
          <IconInput icon={KeyRound} id="mfa-code" required autoFocus value={code} autoComplete="one-time-code"
            onChange={(e) => setCode(e.target.value)} placeholder="123456 or XXXX-XXXX" className="tracking-widest font-mono" />
        </div>

        <SubmitButton busy={submitting}>{submitting ? 'Verifying...' : 'Verify & sign in'}</SubmitButton>

        <button type="button" onClick={() => { setMfaToken(null); setCode(''); setError(null); }}
          className="w-full text-sm text-muted hover:text-ink font-semibold cursor-pointer">
          &larr; Back to login
        </button>
      </form>
    );
  }

  return (
    <form onSubmit={handlePasswordSubmit} className="space-y-4">
      <div>
        <h2 className="text-2xl">Welcome back</h2>
        <p className="text-sm text-muted mt-1">Sign in to your decks.</p>
      </div>

      {notice && (
        <div className="banner-ok" data-testid="signin-done">
          <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
          <p>{notice}</p>
        </div>
      )}
      <ErrorBanner message={error} />
      <PauseHint failures={failures} />

      <div>
        <label className="label" htmlFor="login-username">Username</label>
        <IconInput icon={User} id="login-username" required autoFocus value={username} autoComplete="username"
          onChange={(e) => setUsername(e.target.value)} />
      </div>

      <div>
        <label className="label" htmlFor="login-password">Password</label>
        <IconInput icon={Lock} id="login-password" required type="password" value={password} autoComplete="current-password"
          onChange={(e) => setPassword(e.target.value)} />
      </div>

      <SubmitButton busy={submitting}>{submitting ? 'Signing in...' : 'Sign in'}</SubmitButton>
      <ForgotPassword />
    </form>
  );
}

export default function AuthGateway() {
  const { setupRequired, registrationOpen, inviteOnly, signedOutNotice } = useAuth();
  const [linkCode] = useState(inviteFromUrl);
  const [resetToken, setResetToken] = useState(resetFromUrl);
  const [notice, setNotice] = useState(signedOutNotice || null);
  const [mode, setMode] = useState(setupRequired || linkCode ? 'register' : 'login');
  const canRegister = registrationOpen || inviteOnly;
  const showRegister = setupRequired || (mode === 'register' && canRegister);

  if (resetToken && !setupRequired) {
    return (
      <AuthShell>
        <ResetPasswordForm token={resetToken} onDone={(username) => {
          setResetToken('');
          setMode('login');
          if (username) setNotice(`Password set for ${username}. Sign in with it now.`);
        }} />
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      {showRegister ? <RegisterForm needsInvite={inviteOnly} initialCode={linkCode} /> : <LoginForm notice={notice} />}

      {!setupRequired && canRegister && (
        <p className="text-sm text-muted text-center">
          {showRegister ? 'Already have an account? ' : inviteOnly ? 'Got an invite? ' : 'New to Dose? '}
          <button type="button" onClick={() => setMode(showRegister ? 'login' : 'register')}
            className="text-brand-600 hover:text-brand-700 dark:text-brand-300 font-bold cursor-pointer">
            {showRegister ? 'Sign in' : inviteOnly ? 'Sign up with your code' : 'Create an account'}
          </button>
        </p>
      )}
    </AuthShell>
  );
}
