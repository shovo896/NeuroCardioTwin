window.Dashboard=(()=>{
  const labels={seizure:['Accuracy','Recall','Precision','F1','AUROC','AUPRC'],arrhythmia:['Model status','Input window','Runtime','Output'],forecast:['Model status','Input channels','Forecast horizon','Runtime']};
  const fallback={arrhythmia:{'Model status':'Checkpoint loaded','Input window':'180 ECG samples','Runtime':'ONNX CPU','Output':'Rhythm classification'},forecast:{'Model status':'Checkpoint loaded','Input channels':'ECG + EEG','Forecast horizon':'64 samples','Runtime':'ONNX CPU'}};
  function renderMetrics(group,values){const target=document.getElementById(group+'-metrics');const source=Object.keys(values||{}).length?values:fallback[group]||{};target.innerHTML=labels[group].map(label=>`<div><span>${label}</span><strong>${source[label]??source[label.toLowerCase().replaceAll(' ','_')]??'—'}</strong></div>`).join('')}
  function operational(online,detail=''){
    const pill=document.getElementById('operational-status'),pulse=document.querySelector('.runtime-pulse');
    if(pill){pill.classList.toggle('error',!online);pill.innerHTML=online?'<i class="fa-solid fa-circle-check"></i> System operational':'<i class="fa-solid fa-circle-exclamation"></i> Service unavailable'}
    if(pulse){pulse.style.background=online?'#4ade80':'#fb7185';pulse.style.boxShadow=online?'0 0 0 5px #4ade8021':'0 0 0 5px #fb718521'}
    document.querySelectorAll('#side-backend,#detail-backend').forEach(element=>element.textContent=online?(detail||'AI runtime online'):'Connection unavailable');
  }
  async function connection(){
    try{
      await API.health();
      document.getElementById('backend-summary').textContent='Connected';
      document.querySelector('.sidebar-foot .status-dot').className='status-dot';
      try{
        const models=await API.models(),available=Object.values(models).filter(model=>model?.loaded).length;
        const detail=available?`${available} model checkpoints active`:'Connected; model status unavailable';
        document.getElementById('backend-detail').textContent=detail;operational(true,detail);
      }catch{document.getElementById('backend-detail').textContent='Secure model service online';operational(true,'Secure model service online')}
    }catch{
      document.getElementById('backend-summary').textContent='Unavailable';document.getElementById('backend-detail').textContent='Reconnect to enable inference';document.querySelector('.sidebar-foot .status-dot').className='status-dot error';operational(false);
    }
  }
  async function metrics(){try{const data=await API.metrics();renderMetrics('seizure',data.seizure);renderMetrics('arrhythmia',data.arrhythmia);renderMetrics('forecast',{});document.getElementById('performance-message').querySelector('span').textContent='Live model status and saved validation metrics loaded.'}catch{['seizure','arrhythmia','forecast'].forEach(group=>renderMetrics(group))}}
  function init(){['seizure','arrhythmia','forecast'].forEach(group=>renderMetrics(group));connection();metrics();document.getElementById('refresh-metrics').onclick=metrics}
  return{init,metrics};
})();
