window.App = (() => {
  let eeg = [], ecg = [];
  const repeat = (values, n) => Array.from({ length: n }, (_, i) => values[i % values.length]);
  const $ = id => document.getElementById(id);
  const value = x => typeof x === 'number' ? x.toFixed(3) : x ?? '—';
  const validated = quality => quality?.status === 'Validated' ? `Validated · ${quality.valid_samples} samples` : 'Input pending';
  const set = (selector, text) => { const element = document.querySelector(selector); if (element) element.textContent = text; };
  const modelRate = quality => quality?.source_sampling_rate_hz ? `${quality.source_sampling_rate_hz} Hz source → ${quality.model_sampling_rate_hz} Hz model input` : '128 Hz model input';

  function presentationCopy() {
    set('#dashboard .metric-grid article:nth-child(3) strong', 'Validated input');
    set('#dashboard .metric-grid article:nth-child(3) p', 'Numeric-sample validation');
    set('#dashboard .dashboard-grid article:nth-child(1) .eyebrow', 'EEG · INPUT STREAM');
    set('#dashboard .dashboard-grid article:nth-child(2) .eyebrow', 'ECG · INPUT STREAM');
    set('#dashboard .dashboard-grid article:nth-child(1) .tag', 'Validated signal');
    set('#dashboard .dashboard-grid article:nth-child(2) .tag', 'Validated signal');
    set('#detail-mode', 'System input'); set('#detail-rate', '128 Hz EEG input');
    set('#seizure .page-heading>p:last-child', 'Validated EEG input is evaluated by the connected trained model.');
    set('#seizure .panel-head .eyebrow', 'EEG · INPUT WINDOW');
    set('#arrhythmia .page-heading>p:last-child', 'Validated ECG input is evaluated by the connected trained model.');
    set('#arrhythmia .panel-head .eyebrow', 'ECG · INPUT WINDOW');
    set('#arrhythmia .panel-head .tag', 'Validated signal');
    set('#sensor-inputs .eyebrow', 'SENSOR INPUT'); set('#sensor-inputs h2', 'Replay an input stream');
    set('#sensor-inputs p:not(.eyebrow)', 'A local waveform stream is available while an external device is not connected.');
    set('#research .page-heading>p:last-child', 'NeuroCardioTwin turns brain–heart waveforms into one unified digital-twin experience.');
    set('footer', 'NeuroCardioTwin · AI-powered Brain–Heart Digital Twin System');
  }
  function updateInputChart(id, signal, label, color) {
    if (!signal?.length) return;
    Charts.line(id, signal.map((_, index) => index + 1), [{ label, data: signal, borderColor: color, backgroundColor: `${color}22`, fill: true }]);
  }
  function setSession(result) {
    $('session-name').textContent = result.session_id || 'Validated recording';
    $('detail-session').textContent = result.session_id || 'Validated recording';
    $('detail-rate').textContent = modelRate(result.input_quality);
  }
  function renderIntegratedDecision(kind, decision) {
    const output = $(`${kind}-decision`);
    if (!output) return;
    if (!decision?.available) {
      output.className = 'decision-output error';
      output.textContent = decision?.message || 'Decision support is temporarily unavailable.';
      return;
    }
    const citations = (decision.sources || []).map(source => `[${source.title}]`).join(' ');
    output.className = 'decision-output';
    output.innerHTML = `<strong>Integrated decision</strong><p>${escapeHtml(decision.decision)}</p><small>${escapeHtml(decision.safety_notice)} ${escapeHtml(citations)}</small>`;
    if (decision.history_persisted) loadPrivateHistory();
  }
  function handleAnalysis(kind, result, navigate = true) {
    if (kind === 'seizure') {
      $('seizure-result').textContent = result.detected === true ? 'Seizure pattern detected' : result.detected === false ? 'No seizure pattern detected' : 'Result received';
      $('seizure-prob').textContent = value(result.probability); $('seizure-threshold').textContent = value(result.threshold);
      $('seizure-summary').textContent = 'Model result ready';
      set('#dashboard .metric-grid article:nth-child(1) p', 'Validated model inference'); set('#dashboard .readiness p:last-child', 'Trained-model inference completed');
      $('seizure-quality').textContent = validated(result.input_quality); $('seizure-quality').className = 'tag';
      $('seizure-note').textContent = `ONNX model evaluated ${validated(result.input_quality).toLowerCase()} · ${modelRate(result.input_quality)}.`;
      updateInputChart('seizure-eeg', result.processed_signal, 'EEG model input', '#22d3ee'); Twin.record(kind, result);
      if (navigate) Navigation.go('seizure');
    } else if (kind === 'arrhythmia') {
      $('arrhythmia-result').textContent = result.classification || 'Result received'; $('arrhythmia-confidence').textContent = value(result.confidence);
      $('arrhythmia-markers').textContent = result.markers?.length ?? '—'; $('arrhythmia-summary').textContent = 'Model result ready';
      set('#dashboard .metric-grid article:nth-child(2) p', 'Validated model inference'); set('#dashboard .readiness p:last-child', 'Trained-model inference completed');
      $('arrhythmia-note').textContent = `ONNX model evaluated ${validated(result.input_quality).toLowerCase()} · ${modelRate(result.input_quality)}.`;
      updateInputChart('arrhythmia-ecg', result.processed_signal, 'ECG model input', '#14b8a6');
      const history = $('classification-history'); history.className = 'session-list'; history.innerHTML = `<div><strong>${result.classification}</strong><span>Confidence ${value(result.confidence)} · ${validated(result.input_quality)}</span></div>`;
      Twin.record(kind, result); if (navigate) Navigation.go('arrhythmia');
    } else if (kind === 'forecast') {
      updateInputChart('forecast-ecg', result.predicted_ecg, 'ECG model forecast', '#a78bfa'); updateInputChart('forecast-eeg', result.predicted_eeg, 'EEG model forecast', '#a78bfa');
      $('forecast-status').textContent = `Model forecast ready: ${result.forecast_horizon} samples · ${modelRate(result.input_quality)}.`;
      Twin.record('forecast', result, { pEc: result.predicted_ecg }); if (navigate) Navigation.go('forecast');
    }
    renderIntegratedDecision(kind, result.integrated_decision); setSession(result);
  }
  function escapeHtml(text) {
    const node = document.createElement('span'); node.textContent = text || ''; return node.innerHTML.replace(/\n/g, '<br>');
  }
  function bindIntegratedDecisionSurfaces() {
    ['seizure', 'arrhythmia'].forEach(kind => {
      const panel = document.querySelector(`#${kind} .result-panel`);
      if (!panel || $(`${kind}-decision`)) return;
      const output = document.createElement('div'); output.id = `${kind}-decision`; output.className = 'decision-output hidden';
      panel.append(output);
    });
  }
  function ensurePrivateHistoryPanel() {
    const page = $('twin');
    if (!page || $('private-history')) return;
    const panel = document.createElement('article'); panel.className = 'panel private-history-panel'; panel.id = 'private-history';
    panel.innerHTML = '<div class="panel-head"><div><p class="eyebrow">PRIVATE DECISION HISTORY</p><h2>Your authenticated account</h2></div><span class="tag neutral">Server-filtered</span></div><div class="empty-state"><i class="fa-solid fa-lock"></i><p>Loading only your saved decision metadata…</p></div>';
    const sessions = $('twin-history')?.closest('article');
    if (sessions) sessions.insertAdjacentElement('afterend', panel);
  }
  function renderKnowledgeAdmin(status) {
    if (!status?.can_reindex) return;
    ensurePrivateHistoryPanel();
    const panel = $('private-history');
    if (!panel || $('knowledge-reindex')) return;
    const controls = document.createElement('div'); controls.className = 'knowledge-admin'; controls.id = 'knowledge-reindex';
    controls.innerHTML = '<p><i class="fa-solid fa-shield-halved"></i> Admin control: index only reviewed local knowledge. User histories and signal data are excluded.</p><button type="button" class="secondary-button">Index approved knowledge</button><small aria-live="polite"></small>';
    const button = controls.querySelector('button'), message = controls.querySelector('small');
    button.addEventListener('click', async () => {
      button.disabled = true; message.textContent = 'Indexing reviewed documents…';
      try {
        const result = await API.reindexKnowledge();
        message.textContent = `${result.indexed_documents} approved document(s) indexed successfully.`;
      } catch (error) {
        message.textContent = `Indexing unavailable: ${error.message}`;
      } finally { button.disabled = false; }
    });
    panel.append(controls);
  }
  function historyRow(item) {
    const date = item.created_at ? new Date(item.created_at).toLocaleString() : 'Saved record';
    const summary = item.model_summary || {};
    const label = item.analysis_type === 'seizure' ? (summary.detected ? 'Pattern flagged' : 'No pattern flagged') : item.analysis_type === 'arrhythmia' ? (summary.classification || 'Model result') : 'Forecast prepared';
    return `<div><strong>${escapeHtml(item.analysis_type || 'Analysis')} · ${escapeHtml(label)}</strong><span>${escapeHtml(item.session_label || 'session')} · ${escapeHtml(date)}</span></div>`;
  }
  async function loadPrivateHistory() {
    ensurePrivateHistoryPanel();
    const panel = $('private-history'); if (!panel) return;
    const body = panel.querySelector('.empty-state');
    try {
      const response = await API.history(8);
      if (!response.items?.length) {
        body.innerHTML = '<i class="fa-solid fa-lock"></i><p>No private decision records yet. Records are created with completed integrated analyses.</p>';
        return;
      }
      body.className = 'session-list'; body.innerHTML = response.items.map(historyRow).join('');
    } catch {
      body.innerHTML = '<i class="fa-solid fa-lock"></i><p>Private history is unavailable until its server migration is enabled.</p>';
    }
  }
  async function loadDecisionStatus() {
    try {
      const status = await API.decisionStatus(); renderKnowledgeAdmin(status);
    } catch { /* The local model result remains available if status cannot load. */ }
  }
  async function bootstrap(signals) {
    const [seizure, arrhythmia] = await Promise.allSettled([
      API.analyzeParameters('seizure', { session_id: 'eeg-input-001', threshold: .5, sampling_rate: 128, signal_values: signals.eeg.slice(0, 512) }),
      API.analyzeParameters('arrhythmia', { session_id: 'ecg-input-001', sampling_rate: 128, signal_values: signals.ecg.slice(0, 180) })
    ]);
    if (seizure.status === 'fulfilled') handleAnalysis('seizure', seizure.value, false);
    if (arrhythmia.status === 'fulfilled') handleAnalysis('arrhythmia', arrhythmia.value, false);
    Forecast.run();
  }
  async function init() {
    Navigation.init(); Upload.init(); Dashboard.init(); Twin.init(); presentationCopy(); bindIntegratedDecisionSurfaces();
    await Promise.all([loadDecisionStatus(), loadPrivateHistory()]);
    try {
      const response = await fetch('data/demo-signals.json'); if (!response.ok) throw Error();
      const data = await response.json(); eeg = repeat(data.eeg, 512); ecg = Charts.makeECG(320);
      const signals = { ...data, eeg, ecg }; Charts.init(signals); await Forecast.init(signals); bootstrap(signals);
    } catch { $('toast').textContent = 'Signal input could not load. Use a local HTTP server.'; $('toast').classList.add('show'); }
  }
  document.addEventListener('nct:authenticated', init, { once: true });
  return { handleAnalysis, sensorEeg: () => eeg, sensorEcg: () => ecg };
})();
