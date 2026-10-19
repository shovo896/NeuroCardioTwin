"""ONNX inference API plus an Auth0-protected MCP resource server."""
from pathlib import Path
import json,io
import numpy as np, onnxruntime as ort
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from backend.security import MCP_SCOPES, auth0_ready, mcp_resource, mcp_unauthorized_headers, store, verify_bearer
ROOT=Path(__file__).resolve().parents[1];app=FastAPI(title='NeuroCardioTwin');sessions={}
def start():
    for n in ('seizure','arrhythmia','forecast'):
        p=ROOT/'models'/n/'best_fp32.onnx';sessions[n]=ort.InferenceSession(str(p),providers=['CPUExecutionProvider']) if p.exists() else None
@app.on_event('startup')
def setup():start()
@app.get('/api/health')
def health():return {'status':'ok','runtime':'onnx-cpu','system':'NeuroCardioTwin'}
@app.get('/api/security/status')
def security_status():
    return {'supabase':{'configured':store.configured},'auth0':{'configured':auth0_ready()},'mcp':{'enabled':store.configured and auth0_ready()}}
@app.get('/api/models/status')
def status():return {n:{'loaded':m is not None} for n,m in sessions.items()}
@app.get('/api/capabilities')
def capabilities():
    ready=sessions.get('forecast') is not None
    return {'forecast':{'available':ready,'input_samples':{'ecg':256,'eeg':256},'horizons':[64] if ready else []}}
@app.get('/api/metrics')
def metrics():
    return {n:json.loads(p.read_text()) if (p:=ROOT/'models'/n/'metrics.json').exists() else {} for n in sessions}
MODEL_SAMPLING_RATE=128.0
def sampling_rate(payload):
    try: rate=float(payload.get('sampling_rate',MODEL_SAMPLING_RATE))
    except (TypeError,ValueError): raise HTTPException(422,'sampling_rate must be a positive number.')
    if not 1<=rate<=100000: raise HTTPException(422,'sampling_rate must be between 1 and 100000 Hz.')
    return rate
def norm(x,n,rate=MODEL_SAMPLING_RATE):
    x=np.asarray(x,dtype=np.float32).reshape(-1)
    if x.size<n or not np.isfinite(x).all():raise HTTPException(422,f'Provide at least {n} finite signal samples.')
    # The models were trained at 128 Hz. Convert incoming samples to that time base,
    # then retain one fixed model window. This makes sampling_rate part of inference.
    target=max(2,round(x.size*MODEL_SAMPLING_RATE/rate))
    if target!=x.size:x=np.interp(np.linspace(0,x.size-1,target),np.arange(x.size),x).astype(np.float32)
    x=x[:n] if x.size>=n else np.pad(x,(0,n-x.size),mode='edge')
    return (x-x.mean())/(x.std()+1e-6)
def input_quality(x,rate):return {'status':'Validated','valid_samples':int(x.size),'finite_ratio':float(np.isfinite(x).mean()),'source_sampling_rate_hz':rate,'model_sampling_rate_hz':MODEL_SAMPLING_RATE}
async def payload(request,n,key):
    if 'application/json' in request.headers.get('content-type',''):
        b=await request.json();return norm(b.get('signal_values',[]),n,sampling_rate(b)),b
    f=await request.form();up=f.get(key)
    if up is None:raise HTTPException(422,'Provide JSON signal_values or a CSV upload.')
    return norm(np.genfromtxt(io.BytesIO(await up.read()),delimiter=','),n,sampling_rate(f)),f
def run(name,x):return sessions[name].run(None,{'signal':x.astype(np.float32)})[0]
@app.post('/api/analyze/seizure')
async def seizure(request:Request):
    if sessions.get('seizure') is None:raise HTTPException(503,'Seizure model unavailable')
    x,b=await payload(request,512,'eeg_file');p=float(1/(1+np.exp(-run('seizure',x[None,None])[0])));t=float(b.get('threshold',.5));rate=sampling_rate(b);return {'session_id':b.get('session_id','local'),'detected':p>=t,'probability':p,'threshold':t,'processed_signal':x.tolist(),'input_quality':input_quality(x,rate),'prototype':True}
@app.post('/api/analyze/arrhythmia')
async def arrhythmia(request:Request):
    if sessions.get('arrhythmia') is None:raise HTTPException(503,'Arrhythmia model unavailable')
    x,b=await payload(request,180,'ecg_file');p=float(1/(1+np.exp(-run('arrhythmia',x[None,None])[0])));rate=sampling_rate(b);return {'session_id':b.get('session_id','local'),'classification':'Abnormal beat' if p>=.5 else 'Normal beat','confidence':max(p,1-p),'abnormal_probability':p,'markers':[],'processed_signal':x.tolist(),'input_quality':input_quality(x,rate),'prototype':True}
@app.post('/api/analyze/forecast')
async def forecast(request:Request):
    if sessions.get('forecast') is None:raise HTTPException(503,'Forecast model unavailable')
    b=await request.json();rate=sampling_rate(b);x=np.stack((norm(b.get('ecg_values',[]),256,rate),norm(b.get('eeg_values',[]),256,rate)));p=run('forecast',x[None]);return {'session_id':b.get('session_id','local'),'forecast_horizon':64,'predicted_ecg':p[0,0].tolist(),'predicted_eeg':p[0,1].tolist(),'processed_ecg':x[0].tolist(),'processed_eeg':x[1].tolist(),'input_quality':input_quality(x,rate),'prototype':True}

@app.get('/.well-known/oauth-protected-resource/mcp')
def protected_resource_metadata():
    if not auth0_ready():
        raise HTTPException(503,'MCP authorization is not configured.')
    return {
        'resource':mcp_resource(),
        'authorization_servers':[f"https://{__import__('os').environ['AUTH0_DOMAIN'].strip().removeprefix('https://').rstrip('/')}"],
        'scopes_supported':list(MCP_SCOPES),
        'bearer_methods_supported':['header'],
        'resource_name':'NeuroCardioTwin MCP'
    }

def mcp_error(request_id,code,message):
    return {'jsonrpc':'2.0','id':request_id,'error':{'code':code,'message':message}}

@app.post('/mcp')
async def mcp(request:Request):
    try: body=await request.json()
    except Exception:return JSONResponse(mcp_error(None,-32700,'Invalid JSON-RPC payload.'),status_code=400)
    request_id=body.get('id')
    try: identity=verify_bearer(request,'mcp:read')
    except HTTPException as exc:
        if exc.status_code==401:return JSONResponse(mcp_error(request_id,-32001,exc.detail),status_code=401,headers=mcp_unauthorized_headers())
        return JSONResponse(mcp_error(request_id,-32003,exc.detail),status_code=exc.status_code)
    method=body.get('method')
    if method in ('initialize','server/discover'):
        return {'jsonrpc':'2.0','id':request_id,'result':{'protocolVersion':'2025-06-18','serverInfo':{'name':'NeuroCardioTwin','version':'1.0.0'},'capabilities':{'tools':{}}}}
    tools=[
        {'name':'get_my_profile','description':'Return the authenticated user profile and role memberships.','inputSchema':{'type':'object','properties':{}}},
        {'name':'get_twin_status','description':'Return model availability and safe platform status.','inputSchema':{'type':'object','properties':{}}},
    ]
    if method=='tools/list':return {'jsonrpc':'2.0','id':request_id,'result':{'tools':tools}}
    if method!='tools/call':return mcp_error(request_id,-32601,'Method not found.')
    name=(body.get('params') or {}).get('name')
    try:
        if not store.configured:raise RuntimeError('Profile store is not configured.')
        profile=store.upsert_profile(identity)
        if name=='get_my_profile':
            result={'subject':identity.subject,'email':profile.get('email'),'display_name':profile.get('display_name')}
        elif name=='get_twin_status':
            result={'models':{n:m is not None for n,m in sessions.items()},'raw_signal_access':'not exposed through MCP'}
        else:return mcp_error(request_id,-32602,'Unknown tool.')
        store.audit(identity,'mcp.tool_called',{'tool':name})
        return {'jsonrpc':'2.0','id':request_id,'result':{'content':[{'type':'text','text':json.dumps(result)}]}}
    except RuntimeError as exc:
        return {'jsonrpc':'2.0','id':request_id,'result':{'content':[{'type':'text','text':str(exc)}],'isError':True}}
@app.get('/')
def home():return FileResponse(ROOT/'index.html')
app.mount('/',StaticFiles(directory=str(ROOT),html=True),name='static')
