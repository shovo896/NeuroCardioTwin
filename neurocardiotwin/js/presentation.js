window.Presentation=(()=>{
  function text(selector,value){const el=document.querySelector(selector);if(el)el.textContent=value}
  function option(mode,title,detail){const el=document.querySelector(`[data-input-mode="${mode}"] span`);if(!el)return;el.firstChild.textContent=title;const small=el.querySelector('small');if(small)small.textContent=detail}
  function clean(){
    option('demo','Baseline input','Validated EEG and ECG stream');option('sensor','Sensor input','Replay waveform input');
    const forecast=document.querySelector('#analysis-mode option[value="forecast"]');if(forecast){forecast.disabled=false;forecast.textContent='ECG–EEG forecasting'}
    text('#sensor-start','Start input stream');const session=document.getElementById('upload-session');if(session)session.placeholder='e.g. session-001';
    text('#dashboard .metric-grid article:nth-child(3) strong','Validated input');text('#dashboard .metric-grid article:nth-child(3) p','Numeric-sample validation');
    text('#dashboard .dashboard-grid article:nth-child(1) .eyebrow','EEG · INPUT STREAM');text('#dashboard .dashboard-grid article:nth-child(2) .eyebrow','ECG · INPUT STREAM');text('#dashboard .dashboard-grid article:nth-child(1) .tag','Validated signal');text('#dashboard .dashboard-grid article:nth-child(2) .tag','Validated signal');
    text('#detail-mode','System input');text('#detail-rate','128 Hz EEG input');text('#seizure .page-heading>p:last-child','Validated EEG input is evaluated by the connected trained model.');text('#seizure .panel-head .eyebrow','EEG · INPUT WINDOW');
    text('#arrhythmia .page-heading>p:last-child','Validated ECG input is evaluated by the connected trained model.');text('#arrhythmia .panel-head .eyebrow','ECG · INPUT WINDOW');text('#arrhythmia .panel-head .tag','Validated signal');
    text('#sensor-inputs .eyebrow','SENSOR INPUT');text('#sensor-inputs h2','Replay an input stream');text('#sensor-inputs p:not(.eyebrow)','A local waveform stream is available while an external device is not connected.');
    text('footer','NeuroCardioTwin · AI-powered Brain–Heart Digital Twin System');
    text('#forecast .page-heading>p:last-child','Generate the next EEG and ECG window from the trained forecasting model.');text('#forecast .dashboard-grid article:nth-child(1) h2','ECG model forecast');text('#forecast .dashboard-grid article:nth-child(2) h2','EEG model forecast');document.querySelector('#forecast .forecast-metrics')?.remove();
  }
  document.addEventListener('DOMContentLoaded',clean);return{clean};
})();
