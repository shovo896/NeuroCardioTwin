/* A browser-only Auth0 database signup. Password text is never sent to this app's API. */
(function () {
  const form = document.getElementById('signup-form');
  const email = document.getElementById('signup-email');
  const password = document.getElementById('signup-password');
  const confirmation = document.getElementById('signup-confirm-password');
  const submit = document.getElementById('signup-submit');
  const googleButton = document.getElementById('signup-google-button');
  const error = document.getElementById('signup-error');
  const rules = {
    length: document.getElementById('rule-length'), mixed: document.getElementById('rule-mixed'), match: document.getElementById('rule-match')
  };
  const validPassword = () => password.value.length >= 15 && /[a-z]/.test(password.value) && /[A-Z]/.test(password.value) && /\d/.test(password.value);
  const updateRules = () => {
    const checks = { length: password.value.length >= 15, mixed: /[a-z]/.test(password.value) && /[A-Z]/.test(password.value) && /\d/.test(password.value), match: !!password.value && password.value === confirmation.value };
    Object.entries(checks).forEach(([name, met]) => { rules[name].classList.toggle('met', met); rules[name].querySelector('i').className = met ? 'fa-solid fa-circle-check' : 'fa-solid fa-circle'; });
  };
  const showError = (message) => { error.textContent = message; error.classList.add('show'); };
  const clearError = () => { error.textContent = ''; error.classList.remove('show'); };
  const showInboxState = (address, previouslySent = false) => {
    form.hidden = true;
    document.querySelector('.signup-header h1').textContent = 'Check your inbox.';
    document.querySelector('.signup-header p:last-child').textContent = previouslySent
      ? `A verification link was already sent to ${address}. Verify your email, then return and choose “Sign in with email & password”.`
      : `We sent a verification link to ${address}. Verify your email, then return and choose “Sign in with email & password”.`;
    document.querySelector('.signup-footer').innerHTML = '<a href="index.html?login=email">Return to email sign-in</a>';
  };
  const messageTemplate = (message, values = []) => String(message || '').replace(/%d|%s/g, () => String(values.shift() ?? ''));
  const auth0Error = (result) => {
    if (result?.code === 'user_exists') return 'An account already exists for this email. Verify its inbox, then choose “Sign in with email & password”.';
    if (result?.code === 'connection_disabled') return 'Email/password sign-in is not enabled for this application yet. Ask the project owner to enable the Auth0 database connection.';
    // Auth0 intentionally returns this generic response in some duplicate-signup
    // situations to avoid revealing whether an address already has an account.
    if (result?.code === 'invalid_signup' || /invalid sign up/i.test(String(result?.description || ''))) {
      return 'This email could not be registered again. If you already created the account, verify the link in its inbox and then sign in with email and password.';
    }
    if (result?.code === 'invalid_password') {
      const rules = Array.isArray(result?.description?.rules) ? result.description.rules.filter((rule) => !rule.verified).map((rule) => messageTemplate(rule.message, [...(rule.format || [])])) : [];
      return rules.length ? `Password does not meet the Auth0 security policy: ${rules.join('; ')}.` : 'Password does not meet the Auth0 security policy. Use at least 15 characters and avoid common passwords.';
    }
    if (typeof result?.description === 'string' && result.description) return result.description;
    if (typeof result?.message === 'string' && result.message) return result.message;
    return 'Account creation could not be completed. Please try again.';
  };
  const b64url = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  const random = () => b64url(crypto.getRandomValues(new Uint8Array(32)));
  async function continueWithGoogle() {
    clearError(); googleButton.disabled = true; googleButton.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Connecting to Google…';
    try {
      const response = await fetch('/api/auth/config', { credentials: 'same-origin' });
      if (!response.ok) throw new Error('Google sign-in is not configured yet.');
      const config = await response.json(); const verifier = random(); const state = random();
      const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
      sessionStorage.setItem('nct.oauth.verifier', verifier); sessionStorage.setItem('nct.oauth.state', state);
      const query = new URLSearchParams({ response_type: 'code', client_id: config.client_id, redirect_uri: `${window.location.origin}/`, scope: 'openid profile email mcp:read', audience: config.audience, connection: config.google_connection, prompt: 'select_account', code_challenge: b64url(digest), code_challenge_method: 'S256', state });
      window.location.assign(`https://${config.domain}/authorize?${query}`);
    } catch (reason) {
      showError(reason.message || 'Google sign-in could not be started.'); googleButton.disabled = false; googleButton.innerHTML = '<i class="fa-brands fa-google"></i> Continue with Google';
    }
  }
  [password, confirmation].forEach((field) => field.addEventListener('input', () => { updateRules(); clearError(); }));
  document.querySelectorAll('[data-password-toggle]').forEach((toggle) => toggle.addEventListener('click', () => {
    const field = document.getElementById(toggle.dataset.passwordToggle); const show = field.type === 'password';
    field.type = show ? 'text' : 'password'; toggle.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    toggle.querySelector('i').className = show ? 'fa-regular fa-eye-slash' : 'fa-regular fa-eye';
  }));
  form.addEventListener('submit', async (event) => {
    event.preventDefault(); clearError();
    if (!email.validity.valid) return showError('Enter a valid email address.');
    if (!validPassword()) return showError('Use a stronger password that meets every requirement shown above.');
    if (password.value !== confirmation.value) return showError('Passwords do not match.');
    submit.disabled = true; submit.setAttribute('aria-busy', 'true'); submit.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Creating account…';
    try {
      const configResponse = await fetch('/api/auth/config', { credentials: 'same-origin' });
      if (!configResponse.ok) throw new Error('Secure signup is not configured yet.');
      const config = await configResponse.json();
      const response = await fetch(`https://${config.domain}/dbconnections/signup`, {
        method: 'POST', credentials: 'omit', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: config.client_id, connection: config.database_connection, email: email.value.trim(), password: password.value })
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(auth0Error(result));
      // Public connection name only; this makes the post-verification route
      // clear without placing any credential in browser storage.
      sessionStorage.setItem('nct.signup.connection', config.database_connection);
      sessionStorage.setItem('nct.signup.email', email.value.trim().toLowerCase());
      showInboxState(email.value.trim());
    } catch (reason) {
      const attemptedEmail = email.value.trim().toLowerCase();
      const priorEmail = sessionStorage.getItem('nct.signup.email');
      if (/could not be registered again/i.test(String(reason?.message || '')) && priorEmail === attemptedEmail) {
        showInboxState(email.value.trim(), true);
        return;
      }
      showError(reason.message || 'Account creation could not be completed.');
      submit.disabled = false; submit.removeAttribute('aria-busy'); submit.innerHTML = '<i class="fa-solid fa-user-plus"></i> Create secure account';
    }
  });
  googleButton.addEventListener('click', continueWithGoogle);
  updateRules();
})();
