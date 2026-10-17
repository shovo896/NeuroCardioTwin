"""Local-only FastAPI server for trained NeuroCardioTwin research checkpoints."""
from __future__ import annotations
import io,json,sys
from pathlib import Path
import numpy as np,torch
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));from backend.models import SeizureClassifier,ArrhythmiaClassifier,TwinForecaster
app=FastAPI(title='NeuroCardioTwin local research API'); DEVICE=torch.device('cpu'); registry={}
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
def health(): return {'status':'ok','device':str(DEVICE),'research_only':True}
@app.get('/api/models/status')
def status(): return {k:{'loaded':v is not None,'checkpoint':str(checkpoint(k).relative_to(ROOT))} for k,v in registry.items()}
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
@app.post('/api/analyze/seizure')
async def seizure(request:Request):
    model=registry.get('seizure')
    if model is None:raise HTTPException(503,'Seizure checkpoint is unavailable. Run scripts/train_seizure.py first.')
    form=await request.form();file=form.get('eeg_file') or (form.getlist('eeg_files')[0] if form.getlist('eeg_files') else None)
    if file is None:raise HTTPException(422,'Submit a one-column EEG CSV as eeg_file. EDF parsing is not enabled in this CPU starter server.')
    if not getattr(file,'filename','').lower().endswith('.csv'):raise HTTPException(415,'Only CSV is supported by this starter server.')
    x=csv_signal(await file.read(),512);prob=float(torch.sigmoid(model(torch.tensor(x)[None,None])).item())
    return {'session_id':form.get('session_id') or 'local-upload','detected':prob>=.5,'probability':prob,'threshold':.5,'quality':'not assessed','research_only':True}
@app.post('/api/analyze/arrhythmia')
async def arrhythmia(): raise HTTPException(503,'Train and implement the arrhythmia serving path before use; no prediction is fabricated.')
@app.post('/api/analyze/forecast')
async def forecast(): raise HTTPException(503,'Train and implement the forecasting serving path before use; no prediction is fabricated.')
@app.post('/api/generate-signal')
async def generate_signal(): raise HTTPException(501,'Text-to-signal generation has no validated model in this project. It remains disabled instead of producing a fabricated medical signal.')
app.mount('/static',StaticFiles(directory=str(ROOT)),name='static')
@app.get('/')
def homepage(): return FileResponse(ROOT/'index.html')
app.mount('/',StaticFiles(directory=str(ROOT),html=True),name='frontend')
