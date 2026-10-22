"""ONNX inference API plus an Auth0-protected MCP resource server."""
from pathlib import Path
import json,io
import numpy as np, onnxruntime as ort
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from backend.security import MCP_SCOPES, auth0_ready, mcp_resource, mcp_unauthorized_headers, store, verify_bearer
from backend.decision_support import DecisionConfig, RAGDecisionService, compact_analysis
from starlette.concurrency import run_in_threadpool
ROOT=Path(__file__).resolve().parents[1];app=FastAPI(title='NeuroCardioTwin');sessions={}
def start():
    for n in ('seizure','arrhythmia','forecast'):
        p=ROOT/'models'/n/'best_fp32.onnx';sessions[n]=ort.InferenceSession(str(p),providers=['CPUExecutionProvider']) if p.exists() else None
@app.on_event('startup')
def setup():start()
@app.get('/api/health')
def health(request:Request):
    verify_bearer(request,'mcp:read')
    return {'status':'ok','runtime':'onnx-cpu','system':'NeuroCardioTwin'}
@app.get('/api/security/status')
def security_status():
    return {'supabase':{'configured':store.configured},'auth0':{'configured':auth0_ready()},'mcp':{'enabled':store.configured and auth0_ready()}}
@app.get('/api/auth/config')
def auth_config():
    """Public OAuth values for the browser PKCE flow; no credential is returned."""
    import os
    domain=os.getenv('AUTH0_DOMAIN','').strip().removeprefix('https://').rstrip('/')
    client_id=os.getenv('AUTH0_CLIENT_ID','').strip()
    audience=mcp_resource()
    if not domain or not client_id or not audience:
        raise HTTPException(503,'Browser authentication is not configured.')
    # This is a public database-connection name, not a credential.  The
    # browser uses it only for Auth0's hosted Authentication API signup call.
    database_connection=os.getenv('AUTH0_DATABASE_CONNECTION','Username-Password-Authentication').strip()
    google_connection=os.getenv('AUTH0_GOOGLE_CONNECTION','google-oauth2').strip()
    return {'domain':domain,'client_id':client_id,'audience':audience,'database_connection':database_connection,'google_connection':google_connection}
@app.get('/api/me')
def current_user(request:Request):
    """Verify a user token and return only that user's profile.

    Auth0 is the access-control boundary.  Supabase records are useful for
    audit and organisation metadata, but a transient storage/schema problem
    must not turn a successfully verified sign-in into a failed sign-in.
    """
    identity=verify_bearer(request,'mcp:read')
    profile={'subject':identity.subject,'email':identity.email,'display_name':identity.name,'contact_email':identity.email,'avatar_data':None}
    memberships=[]
    try:
        profile=store.workspace_profile(identity)
        saved_profile=store.profile(identity.subject)
        memberships=store.memberships(saved_profile.get('id') if saved_profile else None)
        store.audit(identity,'profile.session_verified',{'surface':'web'})
    except RuntimeError:
        # Keep the workspace available to an authenticated user; persistence
        # will be retried on the next authenticated request.
        pass
    return {**profile,'memberships':memberships}

@app.put('/api/me')
async def update_current_user(request:Request):
    """Save presentation-only profile fields for the verified caller.

    A verified Auth0 sign-in email is deliberately not accepted here: changing
    it must happen at the identity provider and may require re-verification.
    """
    identity=verify_bearer(request,'mcp:read')
    try:
        payload=await request.json()
        profile=store.update_profile_preferences(identity,payload)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503,'Profile saving is not configured. Apply the private profile preferences migration.') from exc
    return profile
def require_workspace_access(request:Request):
    """Every workspace/model endpoint requires the same verified MCP user token."""
    return verify_bearer(request,'mcp:read')

@app.get('/api/decision/status')
def decision_status(request:Request):
    identity=require_workspace_access(request)
    config=DecisionConfig.from_environment()
    return {
        'available':config.ready,
        'history_configured':store.configured,
        'can_reindex':'admin:read' in identity.permissions,
        'privacy':'Only compact local-model summaries are eligible for AI decision support; raw waveforms are excluded.'
    }

@app.post('/api/knowledge/reindex')
async def reindex_knowledge(request:Request):
    """Admin-only, deliberate knowledge ingestion; it never indexes user data."""
    identity=verify_bearer(request,'admin:read')
    try:
        result=await run_in_threadpool(RAGDecisionService().reindex)
        store.audit(identity,'knowledge.reindexed',{'documents':result['indexed_documents']})
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503,'Knowledge indexing is unavailable. Check server-only AI configuration.') from exc

async def integrated_decision(identity,analysis_type,model_result):
    """Combine a local model result with approved knowledge on the server.

    The browser never orchestrates this flow and raw waveform arrays are
    discarded by ``compact_analysis`` before any provider call is made.
    """
    summary=compact_analysis(analysis_type,model_result)
    try:
        result=await run_in_threadpool(RAGDecisionService().decide,summary)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503,'AI decision support is temporarily unavailable. Verify the server-only provider configuration and knowledge index.') from exc
    persisted=False
    try:
        store.save_private_history(
            identity,
            summary['analysis_type'],
            summary['session_id'],
            summary,
            result['decision'],
            [source['title'] for source in result['sources']],
        )
        store.audit(identity,'decision.generated',{'analysis_type':summary['analysis_type']})
        persisted=True
    except RuntimeError:
        # The response is still useful when Supabase is momentarily offline;
        # silently avoid turning a provider result into a data-loss claim.
        pass
    return {**result,'history_persisted':persisted}

async def attach_integrated_decision(identity,analysis_type,model_result):
    """Keep the local inference usable if optional knowledge services are down."""
    try:
        model_result['integrated_decision']={
            'available':True,
            **await integrated_decision(identity,analysis_type,model_result),
        }
    except Exception as exc:
        # Server logs retain only an exception category for operational
        # diagnosis; no waveform, token, email, or Auth0 subject is logged.
        __import__('logging').getLogger(__name__).warning('Decision support unavailable: %s',type(exc).__name__)
        # This deliberately returns no provider details to the browser.  The
        # local ONNX model remains the source of the displayed result.
        model_result['integrated_decision']={
            'available':False,
            'message':'Decision support is temporarily unavailable. Please retry the analysis shortly.',
        }
    return model_result

@app.post('/api/decision')
async def decision(request:Request):
    """Compatibility endpoint for non-browser clients using the same server flow."""
    identity=require_workspace_access(request)
    try:
        body=await request.json()
    except Exception as exc:
        raise HTTPException(422,'Provide a JSON decision request.') from exc
    if not isinstance(body,dict) or not isinstance(body.get('model_result'),dict):
        raise HTTPException(422,'Provide analysis_type and a model_result object.')
    return await integrated_decision(identity,str(body.get('analysis_type','')),body['model_result'])

@app.post('/api/chat')
async def workspace_chat(request:Request):
    """Private RAG chat; messages are processed transiently and never stored."""
    identity=require_workspace_access(request)
    try:
        body=await request.json()
    except Exception as exc:
        raise HTTPException(422,'Provide a JSON chat request.') from exc
    if not isinstance(body,dict):
        raise HTTPException(422,'Provide a chat message.')
    result=await run_in_threadpool(RAGDecisionService().chat,body.get('message'),body.get('language','en'))
    try: store.audit(identity,'assistant.chat',{'language':result['language']})
    except RuntimeError: pass
    return result

@app.get('/api/history')
def private_history(request:Request,limit:int=20):
    identity=require_workspace_access(request)
    try:
        return {'items':store.private_history(identity,limit)}
    except RuntimeError as exc:
        raise HTTPException(503,'Private history is not configured. Apply the supplied Supabase migration.') from exc

@app.get('/api/models/status')
def status(request:Request):
    require_workspace_access(request);return {n:{'loaded':m is not None} for n,m in sessions.items()}
@app.get('/api/capabilities')
def capabilities(request:Request):
    require_workspace_access(request)
    ready=sessions.get('forecast') is not None
    return {'forecast':{'available':ready,'input_samples':{'ecg':256,'eeg':256},'horizons':[64] if ready else []}}
@app.get('/api/metrics')
def metrics(request:Request):
    require_workspace_access(request)
    return {n:json.loads(p.read_text()) if (p:=ROOT/'models'/n/'metrics.json').exists() else {} for n in sessions}
MODEL_SAMPLING_RATE=128.0
MIN_INPUT_SAMPLES=128
def sampling_rate(payload):
    value=payload.get('sampling_rate',MODEL_SAMPLING_RATE)
    # Empty form inputs are normal in the upload UI.  Treat them as the
    # documented 128 Hz default instead of letting float('') become a 500.
    if value in (None,''): value=MODEL_SAMPLING_RATE
    try: rate=float(value)
    except (TypeError,ValueError): raise HTTPException(422,'sampling_rate must be a positive number.')
    if not 1<=rate<=100000: raise HTTPException(422,'sampling_rate must be between 1 and 100000 Hz.')
    return rate
def detection_threshold(payload):
    value=payload.get('threshold',.5)
    if value in (None,''): value=.5
    try: threshold=float(value)
    except (TypeError,ValueError): raise HTTPException(422,'threshold must be a number between 0.05 and 0.95.')
    if not .05<=threshold<=.95: raise HTTPException(422,'threshold must be between 0.05 and 0.95.')
    return threshold
def norm(x,n,rate=MODEL_SAMPLING_RATE):
    x=np.asarray(x,dtype=np.float32).reshape(-1)
    if x.size<MIN_INPUT_SAMPLES or not np.isfinite(x).all():raise HTTPException(422,f'Provide at least {MIN_INPUT_SAMPLES} finite signal samples.')
    # The models were trained at 128 Hz. Convert incoming samples to that time base,
    # then retain one fixed model window. This makes sampling_rate part of inference.
    target=max(2,round(x.size*MODEL_SAMPLING_RATE/rate))
    if target!=x.size:x=np.interp(np.linspace(0,x.size-1,target),np.arange(x.size),x).astype(np.float32)
    # The bundled demonstration trace has 128 samples.  The ONNX artefacts
    # still require their fixed input tensor sizes, so shorter valid windows
    # are linearly resampled instead of being edge-padded with invented data.
    if x.size<n:
        x=np.interp(np.linspace(0,x.size-1,n),np.arange(x.size),x).astype(np.float32)
    else:
        x=x[:n]
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
    identity=require_workspace_access(request)
    if sessions.get('seizure') is None:raise HTTPException(503,'Seizure model unavailable')
    x,b=await payload(request,512,'eeg_file');p=float(1/(1+np.exp(-run('seizure',x[None,None])[0])));t=detection_threshold(b);rate=sampling_rate(b)
    result={'session_id':b.get('session_id','local'),'detected':p>=t,'probability':p,'threshold':t,'processed_signal':x.tolist(),'input_quality':input_quality(x,rate),'prototype':True}
    return await attach_integrated_decision(identity,'seizure',result)
@app.post('/api/analyze/arrhythmia')
async def arrhythmia(request:Request):
    identity=require_workspace_access(request)
    if sessions.get('arrhythmia') is None:raise HTTPException(503,'Arrhythmia model unavailable')
    x,b=await payload(request,180,'ecg_file');p=float(1/(1+np.exp(-run('arrhythmia',x[None,None])[0])));rate=sampling_rate(b);t=detection_threshold(b)
    result={'session_id':b.get('session_id','local'),'classification':'Abnormal beat' if p>=t else 'Normal beat','confidence':max(p,1-p),'abnormal_probability':p,'markers':[],'processed_signal':x.tolist(),'input_quality':input_quality(x,rate),'prototype':True}
    return await attach_integrated_decision(identity,'arrhythmia',result)
@app.post('/api/analyze/forecast')
async def forecast(request:Request):
    require_workspace_access(request)
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
