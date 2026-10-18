"""Small ONNX Runtime backend used by the Vercel deployment."""
from pathlib import Path
import json,io
import numpy as np, onnxruntime as ort
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
ROOT=Path(__file__).resolve().parents[1];app=FastAPI(title='NeuroCardioTwin');sessions={}
def start():
    for n in ('seizure','arrhythmia','forecast'):
        p=ROOT/'models'/n/'best_fp32.onnx';sessions[n]=ort.InferenceSession(str(p),providers=['CPUExecutionProvider']) if p.exists() else None
@app.on_event('startup')
def setup():start()
@app.get('/api/health')
def health():return {'status':'ok','runtime':'onnx-cpu','system':'NeuroCardioTwin'}
@app.get('/api/models/status')
def status():return {n:{'loaded':m is not None} for n,m in sessions.items()}
@app.get('/api/capabilities')
def capabilities():
    ready=sessions.get('forecast') is not None
    return {'forecast':{'available':ready,'input_samples':{'ecg':256,'eeg':256},'horizons':[64] if ready else []}}
@app.get('/api/metrics')
def metrics():
    return {n:json.loads(p.read_text()) if (p:=ROOT/'models'/n/'metrics.json').exists() else {} for n in sessions}
def norm(x,n):
    x=np.asarray(x,dtype=np.float32).reshape(-1)
    if x.size<n or not np.isfinite(x).all():raise HTTPException(422,f'Provide at least {n} finite signal samples.')
    x=x[:n];return (x-x.mean())/(x.std()+1e-6)
async def payload(request,n,key):
    if 'application/json' in request.headers.get('content-type',''):
        b=await request.json();return norm(b.get('signal_values',[]),n),b
    f=await request.form();up=f.get(key)
    if up is None:raise HTTPException(422,'Provide JSON signal_values or a CSV upload.')
    return norm(np.genfromtxt(io.BytesIO(await up.read()),delimiter=','),n),f
def run(name,x):return sessions[name].run(None,{'signal':x.astype(np.float32)})[0]
@app.post('/api/analyze/seizure')
async def seizure(request:Request):
    if sessions.get('seizure') is None:raise HTTPException(503,'Seizure model unavailable')
    x,b=await payload(request,512,'eeg_file');p=float(1/(1+np.exp(-run('seizure',x[None,None])[0])));t=float(b.get('threshold',.5));return {'session_id':b.get('session_id','local'),'detected':p>=t,'probability':p,'threshold':t,'prototype':True}
@app.post('/api/analyze/arrhythmia')
async def arrhythmia(request:Request):
    if sessions.get('arrhythmia') is None:raise HTTPException(503,'Arrhythmia model unavailable')
    x,b=await payload(request,180,'ecg_file');p=float(1/(1+np.exp(-run('arrhythmia',x[None,None])[0])));return {'session_id':b.get('session_id','local'),'classification':'Abnormal beat' if p>=.5 else 'Normal beat','confidence':max(p,1-p),'abnormal_probability':p,'markers':[],'prototype':True}
@app.post('/api/analyze/forecast')
async def forecast(request:Request):
    if sessions.get('forecast') is None:raise HTTPException(503,'Forecast model unavailable')
    b=await request.json();x=np.stack((norm(b.get('ecg_values',[]),256),norm(b.get('eeg_values',[]),256)));p=run('forecast',x[None]);return {'session_id':b.get('session_id','local'),'forecast_horizon':64,'predicted_ecg':p[0,0].tolist(),'predicted_eeg':p[0,1].tolist(),'prototype':True}
@app.get('/')
def home():return FileResponse(ROOT/'index.html')
app.mount('/',StaticFiles(directory=str(ROOT),html=True),name='static')
