/* Browser-side MCP discovery client. It reuses the same Auth0 token already
   held in sessionStorage, sends no waveform data, and fails silently because
   MCP discovery must never block the protected research workspace. */
window.MCPClient = (() => {
  const servers = ['workspace', 'knowledge', 'models'];
  const call = async (server, method, params = {}) => {
    const token = window.NCTAuth?.accessToken?.();
    if (!token) throw Error('Sign in is required.');
    const response = await fetch(`/mcp/${server}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' },
      body: JSON.stringify({ jsonrpc: '2.0', id: `${server}-${Date.now()}`, method, params })
    });
    const body = await response.json();
    if (!response.ok || body.error) throw Error(body.error?.message || `MCP server returned ${response.status}`);
    return body.result;
  };
  let discovery = null;
  async function discover() {
    if (discovery) return discovery;
    discovery = Promise.all(servers.map(async server => {
      const initialized = await call(server, 'initialize', { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'neurocardiotwin-web', version: '1.0.0' } });
      const tools = await call(server, 'tools/list');
      return { server, name: initialized.serverInfo?.name, tools: (tools.tools || []).map(tool => tool.name) };
    })).catch(error => { discovery = null; throw error; });
    return discovery;
  }
  return { call, discover };
})();
