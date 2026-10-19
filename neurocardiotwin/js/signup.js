/* A browser-only Auth0 database signup. Password text is never sent to this app's API. */
(function () {
  const form = document.getElementById('signup-form');
  const email = document.getElementById('signup-email');
  const password = document.getElementById('signup-password');
  const confirmation = document.getElementById('signup-confirm-password');
  const submit = document.getElementById('signup-submit');
  const error = document.getElementById('signup-error');
  const rules = {
    length: document.getElementById('rule-length'), mixed: document.getElementById('rule-mixed'), match: document.getElementById('rule-match')
  };
  const validPassword = () => password.value.length >= 10 && /[a-z]/.test(password.value) && /[A-Z]/.test(password.value) && /\d/.test(password.value);
  const updateRules = () => {
    const checks = { length: password.value.length >= 10, mixed: /[a-z]/.test(password.value) && /[A-Z]/.test(password.value) && /\d/.test(password.value), match: !!password.value && password.value === confirmation.value };
    Object.entries(checks).forEach(([name, met]) => { rules[name].classList.toggle('met', met); rules[name].querySelector('i').className = met ? 'fa-solid fa-circle-check' : 'fa-solid fa-circle'; });
  };
  const showError = (message) => { error.textContent = message; error.classList.add('show'); };
  const clearError = () => { error.textContent = ''; error.classList.remove('show'); };
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
      if (!response.ok) throw new Error(result.description || result.message || 'Account creation could not be completed.');
      form.hidden = true;
      document.querySelector('.signup-header h1').textContent = 'Check your inbox.';
      document.querySelector('.signup-header p:last-child').textContent = `We sent a verification link to ${email.value.trim()}. Verify your email, then return here to sign in.`;
      document.querySelector('.signup-footer').innerHTML = '<a href="index.html">Return to secure sign-in</a>';
    } catch (reason) {
      showError(reason.message || 'Account creation could not be completed.');
      submit.disabled = false; submit.removeAttribute('aria-busy'); submit.innerHTML = '<i class="fa-solid fa-user-plus"></i> Create secure account';
    }
  });
  updateRules();
})();
