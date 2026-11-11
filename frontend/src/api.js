import axios from 'axios';

// Relative: served via the Vite proxy in dev, or the same host in production.
const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
  // Required so the httpOnly refresh-token cookie is sent/received.
  withCredentials: true,
});

// --------------------------------------------------------------------------
// In-memory access token handling.
//
// The access token is deliberately kept ONLY in memory (never localStorage
// or a JS-readable cookie) to minimize exposure to XSS. AuthContext wires
// itself up via setAccessToken()/setOnAuthExpired() on mount. When a request
// gets a 401, we attempt exactly one silent refresh (using the httpOnly
// refresh cookie) before giving up and forcing a re-login.
// --------------------------------------------------------------------------
let accessToken = null;
let onAuthExpired = null;
let refreshPromise = null;

export const setAccessToken = (token) => {
  accessToken = token;
};

export const setOnAuthExpired = (callback) => {
  onAuthExpired = callback;
};

api.interceptors.request.use((config) => {
  if (accessToken && !config._skipAuth) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const status = error.response?.status;
    const isAuthEndpoint = originalRequest?.url?.startsWith('/auth/');

    if (status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      originalRequest._retry = true;
      try {
        if (!refreshPromise) {
          refreshPromise = api.post('/auth/refresh', null, { _skipAuth: true }).finally(() => {
            refreshPromise = null;
          });
        }
        const { data } = await refreshPromise;
        setAccessToken(data.access_token);
        originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
        return api(originalRequest);
      } catch (refreshErr) {
        setAccessToken(null);
        if (onAuthExpired) onAuthExpired();
        return Promise.reject(refreshErr);
      }
    }

    return Promise.reject(error);
  }
);

// --------------------------------------------------------------------------
// Authentication & Security
// --------------------------------------------------------------------------

export const getBootstrapStatus = async () => {
  const res = await api.get('/auth/bootstrap-status', { _skipAuth: true });
  return res.data;
};

export const register = async ({ username, password, email, householdName, inviteCode }) => {
  const res = await api.post(
    '/auth/register',
    { username, password, email, household_name: householdName, invite_code: inviteCode || null },
    { _skipAuth: true },
  );
  return res.data;
};

// What an invite link is for (shown before signing up with it).
export const checkInvite = async (code) => {
  const res = await api.get('/auth/invites/check', { params: { code }, _skipAuth: true });
  return res.data;
};

export const login = async (username, password) => {
  const res = await api.post('/auth/login', { username, password }, { _skipAuth: true });
  return res.data;
};

export const verifyTwoFactor = async (mfaToken, code) => {
  const res = await api.post('/auth/login/verify-2fa', { mfa_token: mfaToken, code }, { _skipAuth: true });
  return res.data;
};

// Concurrent callers share one refresh: refresh tokens rotate, and presenting
// the same one twice looks like token theft (the server then revokes the
// session). React's StrictMode runs the startup refresh twice in development.
export const refreshSession = async () => {
  if (!refreshPromise) {
    refreshPromise = api.post('/auth/refresh', null, { _skipAuth: true }).finally(() => {
      refreshPromise = null;
    });
  }
  const res = await refreshPromise;
  return res.data;
};

export const logout = async () => {
  const res = await api.post('/auth/logout');
  return res.data;
};

export const logoutAllDevices = async () => {
  const res = await api.post('/auth/logout-all');
  return res.data;
};

export const getMe = async () => {
  const res = await api.get('/auth/me');
  return res.data;
};

export const changePassword = async (currentPassword, newPassword) => {
  const res = await api.post('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  });
  return res.data;
};

export const setupTwoFactor = async () => {
  const res = await api.post('/auth/2fa/setup');
  return res.data;
};

export const confirmTwoFactor = async (code) => {
  const res = await api.post('/auth/2fa/confirm', { code });
  return res.data;
};

export const disableTwoFactor = async (password, code) => {
  const res = await api.post('/auth/2fa/disable', { password, code });
  return res.data;
};

export const regenerateBackupCodes = async (password) => {
  const res = await api.post('/auth/2fa/backup-codes/regenerate', { password });
  return res.data;
};

export const listUsers = async () => {
  const res = await api.get('/auth/users');
  return res.data;
};

export const createUser = async (userData) => {
  const res = await api.post('/auth/users', userData);
  return res.data;
};

export const deactivateUser = async (userId) => {
  const res = await api.delete(`/auth/users/${userId}`);
  return res.data;
};

// Lets someone sign in from a new device while wrong passwords have paused their account.
export const clearUserLock = async (userId) => {
  const res = await api.post(`/auth/users/${userId}/clear-lock`);
  return res.data;
};

// --------------------------------------------------------------------------
// Invites (invite-only sign-up)
// --------------------------------------------------------------------------

export const listInvites = async () => (await api.get('/auth/invites')).data;

export const createInvite = async (invite) => (await api.post('/auth/invites', invite)).data;

// Reset links (no email): admins for their members, the instance owner for admins. Shown once.
export const makeResetLink = async (userId) => (await api.post(`/auth/users/${userId}/reset-link`)).data;

export const getOtherAdmins = async () => (await api.get('/auth/other-admins')).data;

export const checkResetLink = async (token) =>
  (await api.get('/auth/reset/check', { params: { token }, _skipAuth: true })).data;

export const resetPassword = async (token, newPassword) =>
  (await api.post('/auth/reset', { token, new_password: newPassword }, { _skipAuth: true })).data;

export const revokeInvite = async (inviteId) => (await api.delete(`/auth/invites/${inviteId}`)).data;

export const getRegistrationSettings = async () => (await api.get('/settings/registration')).data;

// Only the fields given change: { mode } and/or { public_url } ('' clears it).
export const updateRegistrationSettings = async (changes) => (await api.post('/settings/registration', changes)).data;

// Server keys (instance owner): where they live, what each opens, and moving to a new one.
export const getServerKeys = async () => (await api.get('/settings/keys')).data;
export const rotateDataKeys = async (password) => (await api.post('/settings/keys/rotate', { password })).data;
export const acceptServerKeys = async (password) => (await api.post('/settings/keys/accept', { password })).data;
export const signOutEveryone = async (password) => (await api.post('/settings/keys/sign-out-everyone', { password })).data;

// AI settings (instance owner). The key is never returned, only whether one is set.
export const getAISettings = async () => (await api.get('/settings/ai')).data;
// anthropic_api_key: omit to keep, "" to clear.
export const updateAISettings = async (changes) => (await api.post('/settings/ai', changes)).data;

// --------------------------------------------------------------------------
// Current: News Front Page, Feed, Sources, Reader, Kept & Settings
// --------------------------------------------------------------------------

// Front page edition & category feeds
export const getFrontpage = async () => (await api.get('/frontpage')).data;
export const getFeed = async (category = '', limit = 30, offset = 0) =>
  (await api.get('/feed', { params: { category: category || undefined, limit, offset } })).data;

// Votes (keep / skip / open) & Undo
export const postVote = async (articleId, verdict) =>
  (await api.post('/votes', { article_id: articleId, verdict })).data;
export const undoVote = async (articleId) => (await api.delete(`/votes/${articleId}`)).data;

// Kept reading list
export const getKept = async (status = 'all', limit = 50, offset = 0) =>
  (await api.get('/kept', { params: { status, limit, offset } })).data;
export const updateKeptState = async (articleId, keptState) =>
  (await api.patch(`/kept/${articleId}`, { kept_state: keptState })).data;

// Reader & full-text on demand
export const getArticle = async (id) => (await api.get(`/articles/${id}`)).data;
export const fetchArticleFulltext = async (id, { force = false, sync = true } = {}) =>
  (await api.post(`/articles/${id}/fetch-text`, null, { params: { force, sync } })).data;

// Sources & Categories
export const getCategories = async () => (await api.get('/categories')).data;
export const createCategory = async (data) => (await api.post('/categories', data)).data;
export const updateCategory = async (id, changes) => (await api.patch(`/categories/${id}`, changes)).data;
export const deleteCategory = async (id) => (await api.delete(`/categories/${id}`)).data;

export const getSources = async () => (await api.get('/sources')).data;
export const probeSource = async (url) => (await api.post('/sources/probe', { url })).data;
export const createSource = async (data) => (await api.post('/sources', data)).data;
export const updateSource = async (id, changes) => (await api.patch(`/sources/${id}`, changes)).data;
export const deleteSource = async (id) => (await api.delete(`/sources/${id}`)).data;
export const crawlSource = async (id, force = false) => (await api.post(`/sources/${id}/crawl`, null, { params: { force } })).data;
export const crawlAll = async () => (await api.post('/crawl')).data;
export const getSourceRuns = async (id) => (await api.get(`/sources/${id}/runs`)).data;

// Crawl & Learning settings
export const getCrawlSettings = async () => (await api.get('/settings/crawl')).data;
export const updateCrawlSettings = async (changes) => (await api.patch('/settings/crawl', changes)).data;
export const getLearningSettings = async () => (await api.get('/settings/learning')).data;
export const muteLearningTerm = async (term) => (await api.post('/settings/learning/mute', { term })).data;
export const unmuteLearningTerm = async (term) => (await api.delete(`/settings/learning/mute/${encodeURIComponent(term)}`)).data;
export const resetLearningModel = async () => (await api.post('/settings/learning/reset')).data;

// Pictures sit behind the sign-in: load the bytes with the access token and hand the <img> a blob URL
export const fetchImageBlob = async (path) => (await api.get(path, { responseType: 'blob' })).data;

export default api;
