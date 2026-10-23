(() => {
  const byId = (id) => document.getElementById(id);
  const label = (enabled, yes = 'Available', no = 'Not configured') => enabled ? yes : no;

  async function loadLiveStatus() {
    const response = await fetch('/api/docs/status', { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(`Status request returned ${response.status}`);
    const status = await response.json();
    const availableModels = Object.values(status.models || {}).filter(Boolean).length;
    byId('docs-runtime').textContent = status.runtime || 'Unknown';
    byId('docs-model-count').textContent = `${availableModels} / 3 available`;
    byId('docs-storage-status').textContent = label(status.private_storage_configured, 'Configured');
    byId('docs-mcp-count').textContent = `${(status.mcp_services || []).length} protected services`;
    byId('docs-live-dot').className = 'status-dot';
    byId('docs-last-updated').textContent = `Updated ${new Date().toLocaleString()}`;
  }

  loadLiveStatus().catch(() => {
    byId('docs-runtime').textContent = 'Status unavailable';
    byId('docs-model-count').textContent = 'Status unavailable';
    byId('docs-storage-status').textContent = 'Status unavailable';
    byId('docs-mcp-count').textContent = 'Status unavailable';
    byId('docs-last-updated').textContent = 'The live status endpoint could not be reached.';
  });
})();
