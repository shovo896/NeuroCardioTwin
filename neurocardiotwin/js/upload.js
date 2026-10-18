window.Upload=(()=>{
  const allowed={ecg:['csv','dat','hea'],eeg:['csv','edf']};
  const samples={seizure:512,arrhythmia:180,forecast:256};
  let sensor=false;
  const $=id=>document.getElementById(id);
  const selected=()=>$('analysis-mode').value;
  const rate=()=>Number($('sample-rate').value)||128;
  function msg(text,ok=false){$('upload-message').textContent=text;$('upload-message').className='form-message '+(ok?'success':'')}
  function req(){const kind=selected(),n=samples[kind];$('sample-requirement').textContent=kind==='forecast'?'256 ECG + 256 EEG samples':`Minimum ${n} samples`}
  function mode(inputMode){
    $('file-inputs').classList.toggle('hidden',inputMode==='parameters'||inputMode==='sensor');$('parameter-inputs').classList.toggle('hidden',inputMode!=='parameters');$('sensor-inputs').classList.toggle('hidden',inputMode!=='sensor');
    $('analysis-submit').innerHTML=inputMode==='sensor'?'<i class="fa-solid fa-play"></i> Analyse sensor stream':inputMode==='demo'?'<i class="fa-solid fa-wave-square"></i> Run baseline analysis':'<i class="fa-solid fa-microscope"></i> Run model detection';
    $('mode-label').innerHTML=inputMode==='sensor'?'<i class="fa-solid fa-tower-broadcast"></i> Sensor input':inputMode==='parameters'?'<i class="fa-solid fa-sliders"></i> Manual parameters':inputMode==='upload'?'<i class="fa-solid fa-file-arrow-up"></i> Signal upload':'<i class="fa-solid fa-circle-check"></i> System input';req();
  }
  function manual(){const values=$('signal-values').value.trim().split(/[\s,;]+/).filter(Boolean).map(Number),n=samples[selected()];if(!values.length||values.some(x=>!Number.isFinite(x)))throw Error('Paste numeric signal values only');if(values.length<n)throw Error(`At least ${n} samples are required; received ${values.length}`);return values}
  function inputStream(channel,amount){const base=channel==='eeg'?window.App.sensorEeg():window.App.sensorEcg();if(!base?.length)throw Error('Signal input is still loading. Try again in a moment.');return Array.from({length:amount},(_,i)=>base[i%base.length])}
  function payload(values,source){return {signal_values:values,session_id:$('upload-session').value||source,sampling_rate:rate(),threshold:Number($('detection-threshold').value)}}
  function forecastPayload(source,ecg,eeg){return {session_id:$('upload-session').value||source,sampling_rate:rate(),ecg_values:ecg,eeg_values:eeg}}
  async function csvValues(file,n,label){if(!file||!file.name.toLowerCase().endsWith('.csv'))throw Error(`${label} forecasting input must be a one-column CSV file.`);const tokens=(await file.text()).trim().split(/[\s,;]+/).filter(Boolean),values=tokens.map(Number);if(!values.length||values.some(v=>!Number.isFinite(v)))throw Error(`${label} CSV must contain numeric samples only.`);if(values.length<n)throw Error(`${label} CSV needs at least ${n} samples.`);return values}
  async function runForecast(inputMode){
    if(inputMode==='parameters')throw Error('Forecasting requires paired ECG and EEG inputs. Use Baseline, Sensor input, or upload two CSV files.');
    if(inputMode==='upload'){const ecg=await csvValues($('ecg-file').files[0],256,'ECG'),eeg=await csvValues($('eeg-file').files[0],256,'EEG');return API.analyzeParameters('forecast',forecastPayload('uploaded-forecast',ecg,eeg))}
    if(inputMode==='sensor'&&!sensor)throw Error('Start the sensor stream first');
    return API.analyzeParameters('forecast',forecastPayload(inputMode==='sensor'?'sensor-forecast':'baseline-forecast',inputStream('ecg',256),inputStream('eeg',256)));
  }
  async function refreshForecastCapability(){const option=$('analysis-mode').querySelector('option[value="forecast"]');try{const capability=(await API.capabilities()).forecast;option.disabled=!capability?.available;option.textContent=capability?.available?'ECG–EEG forecasting':'ECG–EEG forecasting (model offline)'}catch{option.disabled=true;option.textContent='ECG–EEG forecasting (model offline)'}}
  function init(){
    ['ecg','eeg'].forEach(type=>$(type+'-file').addEventListener('change',event=>{const files=event.target.files,ok=[...files].every(file=>allowed[type].includes(file.name.split('.').pop().toLowerCase()));$(type+'-file-name').textContent=files.length?[...files].map(file=>file.name).join(', '):'No file selected';if(!ok)msg('Unsupported file format.')}));
    $('analysis-mode').onchange=req;
    $('sensor-start').onclick=()=>{sensor=true;$('sensor-status').className='tag';$('sensor-status').innerHTML='<i class="fa-solid fa-circle"></i> Stream active';$('sensor-start').innerHTML='<i class="fa-solid fa-rotate"></i> Restart stream';if(!$('upload-session').value)$('upload-session').value='sensor-input-'+Date.now().toString().slice(-6);if(!$('sample-rate').value)$('sample-rate').value='128';msg('Sensor input is active. Analyse the waveform now.',true)};
    document.querySelectorAll('.mode-option').forEach(button=>button.onclick=()=>{document.querySelectorAll('.mode-option').forEach(item=>{item.classList.remove('active');item.setAttribute('aria-checked','false')});button.classList.add('active');button.setAttribute('aria-checked','true');mode(button.dataset.inputMode);msg(button.dataset.inputMode==='sensor'?'Start the sensor stream, then run detection.':button.dataset.inputMode==='parameters'?'Paste waveform samples, then run detection.':button.dataset.inputMode==='demo'?'Validated EEG/ECG input is ready. Choose a model and run it.':'',true)});
    $('upload-form').onsubmit=async event=>{event.preventDefault();const inputMode=document.querySelector('.mode-option.active').dataset.inputMode,kind=selected();$('upload-progress').classList.remove('hidden');try{let result;if(kind==='forecast')result=await runForecast(inputMode);else if(inputMode==='parameters')result=await API.analyzeParameters(kind,payload(manual(),'manual-input'));else if(inputMode==='sensor'){if(!sensor)throw Error('Start the sensor stream first');result=await API.analyzeParameters(kind,payload(inputStream(kind==='seizure'?'eeg':'ecg',samples[kind]),'sensor-input'))}else if(inputMode==='demo')result=await API.analyzeParameters(kind,payload(inputStream(kind==='seizure'?'eeg':'ecg',samples[kind]),'baseline-input'));else{const file=kind==='seizure'?$('eeg-file').files[0]:$('ecg-file').files[0];if(!file)throw Error('Select the required signal file');const form=new FormData();form.append(kind==='seizure'?'eeg_file':'ecg_file',file);form.append('session_id',$('upload-session').value);form.append('threshold',$('detection-threshold').value);form.append('sampling_rate',rate());result=await API.analyze(kind,form)}window.App.handleAnalysis(kind,result);msg(`Model result received. ${rate()} Hz source input was converted to the model's 128 Hz time base.`,true)}catch(error){msg('Detection was not completed: '+error.message)}finally{$('upload-progress').classList.add('hidden')}};
    req();refreshForecastCapability();
  }
  return {init};
})();
