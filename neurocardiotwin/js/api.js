window.API = {
  base: '',
  async request(path, options = {}) {
    const token = window.NCTAuth?.accessToken?.();
    if (!token) throw Error('Sign in is required.');
    const headers = new Headers(options.headers || {});
    headers.set('Authorization', `Bearer ${token}`);
    const response = await fetch(this.base + path, { ...options, headers });
    if (!response.ok) {
      let message = `Server returned ${response.status}`;
      try { message = (await response.json()).detail || message; } catch { /* safe fallback */ }
      throw Error(message);
    }
    return response.json();
  },
  json(path, payload) { return this.request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); },
  health() { return this.request('/api/health'); },
  models() { return this.request('/api/models/status'); },
  capabilities() { return this.request('/api/capabilities'); },
  metrics() { return this.request('/api/metrics'); },
  analyze(kind, data) { return this.request(`/api/analyze/${kind}`, { method: 'POST', body: data }); },
  analyzeParameters(kind, payload) { return this.json(`/api/analyze/${kind}`, payload); },
  decision(analysisType, modelResult) { return this.json('/api/decision', { analysis_type: analysisType, model_result: modelResult }); },
  decisionStatus() { return this.request('/api/decision/status'); },
  reindexKnowledge() { return this.json('/api/knowledge/reindex', {}); },
  history(limit = 20) { return this.request(`/api/history?limit=${encodeURIComponent(limit)}`); },
  updateProfile(payload) { return this.request('/api/me', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); }
};
