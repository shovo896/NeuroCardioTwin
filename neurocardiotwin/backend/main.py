"""Local-only FastAPI server for the NeuroCardioTwin competition prototype."""
from __future__ import annotations
import io,json,sys
from pathlib import Path
import numpy as np,torch
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));from backend.models import SeizureClassifier,ArrhythmiaClassifier,TwinForecaster
app=FastAPI(title='NeuroCardioTwin Digital Twin API'); DEVICE=torch.device('cpu'); registry={}
def checkpoint(task): return ROOT/'models'/task/'best_fp32.pth'
def load(task):
    path=checkpoint(task)
    if not path.exists(): return None
    cls={'seizure':SeizureClassifier,'arrhythmia':ArrhythmiaClassifier,'forecast':TwinForecaster}[task]; model=cls().to(DEVICE).eval(); state=torch.load(path,map_location=DEVICE,weights_only=True);model.load_state_dict(state['state_dict']);return model
@app.on_event('startup')
def startup():
    for task in ('seizure','arrhythmia','forecast'):
        try: registry[task]=load(task)
        except Exception: registry[task]=None
@app.get('/api/health')
def health(): return {'status':'ok','device':str(DEVICE),'system':'NeuroCardioTwin competition prototype'}
@app.get('/api/models/status')
def status(): return {k:{'loaded':v is not None,'checkpoint':str(checkpoint(k).relative_to(ROOT))} for k,v in registry.items()}
@app.get('/api/capabilities')
def capabilities():
    ready=registry.get('forecast') is not None
    return {'forecast':{'available':ready,'input_samples':{'ecg':256,'eeg':256},'horizons':[64] if ready else []}}
@app.get('/api/metrics')
def metrics():
    out={}
    for task in ('seizure','arrhythmia','forecast'):
        p=ROOT/'models'/task/'metrics.json';out[task]=json.loads(p.read_text()) if p.exists() else {}
    return out
def csv_signal(raw:bytes,n:int):
    values=np.genfromtxt(io.BytesIO(raw),delimiter=',',dtype=np.float32);values=np.asarray(values).squeeze();values=values[np.isfinite(values)]
    if values.size<n:raise HTTPException(422,f'CSV needs at least {n} numeric samples')
    values=values[:n];return (values-values.mean())/(values.std()+1e-6)
async def signal_request(request:Request,n:int,file_key:str):
    if 'application/json' in request.headers.get('content-type',''):
        body=await request.json(); values=np.asarray(body.get('signal_values',[]),dtype=np.float32).reshape(-1)
        if values.size<n or not np.isfinite(values).all():raise HTTPException(422,f'Provide at least {n} finite numeric signal values.')
        x=values[:n];x=(x-x.mean())/(x.std()+1e-6);return x,body
    form=await request.form();file=form.get(file_key) or (form.getlist(file_key+'s')[0] if form.getlist(file_key+'s') else None)
    if file is None:raise HTTPException(422,f'Submit a one-column CSV as {file_key}, or JSON signal_values.')
    if not getattr(file,'filename','').lower().endswith('.csv'):raise HTTPException(415,'Only CSV is supported by this CPU starter server.')
    return csv_signal(await file.read(),n),form
@app.post('/api/analyze/seizure')
async def seizure(request:Request):
    model=registry.get('seizure')
    if model is None:raise HTTPException(503,'Seizure checkpoint is unavailable. Run scripts/train_seizure.py first.')
    x,payload=await signal_request(request,512,'eeg_file');prob=float(torch.sigmoid(model(torch.tensor(x)[None,None])).item());threshold=float(payload.get('threshold',.5))
    if not .05<=threshold<=.95:raise HTTPException(422,'threshold must be between 0.05 and 0.95')
    return {'session_id':payload.get('session_id') or 'local-upload','detected':prob>=threshold,'probability':prob,'threshold':threshold,'quality':'not assessed','prototype':True}
@app.post('/api/analyze/arrhythmia')
async def arrhythmia(request:Request):
    model=registry.get('arrhythmia')
    if model is None:raise HTTPException(503,'Arrhythmia checkpoint is unavailable. Run scripts/train_arrhythmia.py first.')
    x,payload=await signal_request(request,180,'ecg_file');prob=float(torch.sigmoid(model(torch.tensor(x)[None,None])).item());threshold=float(payload.get('threshold',.5))
    return {'session_id':payload.get('session_id') or 'local-upload','classification':'Abnormal beat' if prob>=threshold else 'Normal beat','confidence':max(prob,1-prob),'abnormal_probability':prob,'markers':[],'prototype':True}
@app.post('/api/analyze/forecast')
async def forecast(request:Request):
    model=registry.get('forecast')
    if model is None:raise HTTPException(503,'Forecast checkpoint is unavailable. Run scripts/train_forecast.py first.')
    if 'application/json' not in request.headers.get('content-type',''):raise HTTPException(415,'Submit JSON with ecg_values and eeg_values.')
    body=await request.json(); ecg=np.asarray(body.get('ecg_values',[]),dtype=np.float32).reshape(-1); eeg=np.asarray(body.get('eeg_values',[]),dtype=np.float32).reshape(-1)
    if ecg.size<256 or eeg.size<256 or not np.isfinite(ecg).all() or not np.isfinite(eeg).all():raise HTTPException(422,'Provide at least 256 finite ECG and EEG values.')
    x=np.stack((ecg[:256],eeg[:256]));x=(x-x.mean(1,keepdims=True))/(x.std(1,keepdims=True)+1e-6)
    with torch.inference_mode():pred,quality=model(torch.tensor(x)[None])
    return {'session_id':body.get('session_id') or 'local-forecast','forecast_horizon':64,'predicted_ecg':pred[0,0].tolist(),'predicted_eeg':pred[0,1].tolist(),'signal_reliability':quality[0].tolist(),'prototype':True}
app.mount('/static',StaticFiles(directory=str(ROOT)),name='static')
@app.get('/')
def homepage(): return FileResponse(ROOT/'index.html')
app.mount('/',StaticFiles(directory=str(ROOT),html=True),name='frontend')
