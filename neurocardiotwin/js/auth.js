/* Browser OAuth uses Authorization Code + PKCE. Tokens stay in sessionStorage,
   while Supabase's service key remains server-only in Vercel. */
(function () {
  const TOKEN_KEY = 'nct.oauth.tokens';
  const VERIFIER_KEY = 'nct.oauth.verifier';
  const STATE_KEY = 'nct.oauth.state';
  const redirectUri = window.location.origin + window.location.pathname;
  let config;

  const button = () => document.getElementById('auth-button');
  const gateButton = () => document.getElementById('auth-gate-button');
  const gateMessage = () => document.getElementById('auth-gate-message');
  const tokens = () => {
    try { return JSON.parse(sessionStorage.getItem(TOKEN_KEY) || 'null'); }
    catch { return null; }
  };
  const encode = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  const random = () => encode(crypto.getRandomValues(new Uint8Array(32)));
  const announce = (message, error = false) => {
    const old = document.getElementById('auth-toast');
    if (old) old.remove();
    const toast = document.createElement('div');
    toast.id = 'auth-toast'; toast.className = `auth-toast${error ? ' error' : ''}`;
    toast.textContent = message; document.body.appendChild(toast);
    window.setTimeout(() => toast.remove(), 5000);
  };
  const lock = (message) => {
    document.body.classList.remove('auth-pending', 'authenticated');
    document.body.classList.add('auth-locked');
    const messageEl = gateMessage(); if (messageEl) messageEl.textContent = message;
    const gate = gateButton(); if (gate) gate.disabled = false;
  };
  const unlock = (me) => {
    document.body.classList.remove('auth-pending', 'auth-locked');
    document.body.classList.add('authenticated');
    document.dispatchEvent(new CustomEvent('nct:authenticated', { detail: me }));
  };
  const render = (profile) => {
    const el = button(); if (!el) return;
    if (profile) {
      el.innerHTML = '<i class="fa-solid fa-arrow-right-from-bracket"></i><span>Sign out</span>';
      el.title = profile.email || profile.display_name || 'Signed in';
      el.dataset.signedIn = 'true';
    } else {
      el.innerHTML = '<i class="fa-solid fa-right-to-bracket"></i><span>Sign in</span>';
      el.title = 'Sign in to your workspace'; delete el.dataset.signedIn;
    }
  };
  async function getConfig() {
    if (config) return config;
    const response = await fetch('/api/auth/config', { credentials: 'same-origin' });
    if (!response.ok) throw new Error('Sign-in is not configured yet.');
    config = await response.json(); return config;
  }
  async function profile() {
    const token = tokens()?.access_token;
    if (!token) return null;
    const response = await fetch('/api/me', { headers: { Authorization: `Bearer ${token}` } });
    if (response.ok) return response.json();
    if (response.status === 401 || response.status === 403) {
      sessionStorage.removeItem(TOKEN_KEY);
      throw new Error('Verify your email, then sign in again to activate access.');
    }
    throw new Error('Unable to verify the signed-in session.');
  }
  async function signIn() {
    const oauth = await getConfig();
    const verifier = random(); const state = random();
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
    sessionStorage.setItem(VERIFIER_KEY, verifier); sessionStorage.setItem(STATE_KEY, state);
    const query = new URLSearchParams({
      response_type: 'code', client_id: oauth.client_id, redirect_uri: redirectUri,
      scope: 'openid profile email mcp:read', audience: oauth.audience,
      code_challenge: encode(digest), code_challenge_method: 'S256', state
    });
    window.location.assign(`https://${oauth.domain}/authorize?${query}`);
  }
  async function finishCallback() {
    const query = new URLSearchParams(window.location.search);
    const code = query.get('code');
    if (!code) {
      if (query.get('error')) announce(query.get('error_description') || 'Sign-in was cancelled.', true);
      return;
    }
    if (query.get('state') !== sessionStorage.getItem(STATE_KEY)) {
      throw new Error('Sign-in validation failed. Please try again.');
    }
    const oauth = await getConfig();
    const form = new URLSearchParams({ grant_type: 'authorization_code', client_id: oauth.client_id,
      code, redirect_uri: redirectUri, code_verifier: sessionStorage.getItem(VERIFIER_KEY) || '' });
    const response = await fetch(`https://${oauth.domain}/oauth/token`, {
      method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: form
    });
    const result = await response.json();
    sessionStorage.removeItem(VERIFIER_KEY); sessionStorage.removeItem(STATE_KEY);
    history.replaceState({}, document.title, redirectUri);
    if (!response.ok || !result.access_token) throw new Error(result.error_description || 'Token exchange failed.');
    sessionStorage.setItem(TOKEN_KEY, JSON.stringify(result));
  }
  async function signOut() {
    const oauth = await getConfig(); sessionStorage.removeItem(TOKEN_KEY);
    window.location.assign(`https://${oauth.domain}/v2/logout?${new URLSearchParams({ client_id: oauth.client_id, returnTo: redirectUri })}`);
  }
  window.NCTAuth = { accessToken: () => tokens()?.access_token || null };
  async function boot() {
    try {
      await finishCallback();
      const me = await profile(); render(me);
      if (me) { unlock(me); announce(`Signed in${me.display_name ? ` as ${me.display_name}` : ''}.`); }
      else lock('Sign in with your verified account to access the workspace.');
    } catch (error) { render(null); lock(error.message || 'Sign-in failed.'); }
    const authenticate = async (el) => {
      try {
        el.disabled = true;
        if (el.dataset.signedIn) await signOut(); else await signIn();
      } catch (error) {
        lock(error.message || 'Sign-in failed.'); announce(error.message || 'Sign-in failed.', true); el.disabled = false;
      }
    };
    const topButton = button(); if (topButton) topButton.addEventListener('click', () => authenticate(topButton));
    const signInButton = gateButton(); if (signInButton) signInButton.addEventListener('click', () => authenticate(signInButton));
  }
  // auth.js is loaded after the gate markup, so boot immediately. This also
  // avoids a stale/bfcache document missing the DOMContentLoaded event.
  boot();
})();
