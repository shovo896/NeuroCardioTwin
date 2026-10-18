from __future__ import annotations
import json,sys
from pathlib import Path
import numpy as np,torch,wfdb
from torch.utils.data import DataLoader,TensorDataset
from sklearn.metrics import mean_absolute_error,mean_squared_error,r2_score
sys.path.insert(0,str(Path(__file__).resolve().parents[1])); from backend.models import TwinForecaster
ROOT=Path(__file__).resolve().parents[1]; RAW=ROOT/'data'/'slpdb'; OUT=ROOT/'models'/'forecast'; CTX=256; FUTURE=64
def pair(record,limit=180000):
    h=wfdb.rdheader(str(RAW/record)); names=[x.upper() for x in h.sig_name]; ecg=next(i for i,x in enumerate(names) if 'ECG' in x); eeg=next(i for i,x in enumerate(names) if 'EEG' in x)
    sig,_=wfdb.rdsamp(str(RAW/record),channels=[ecg,eeg],sampto=min(limit,h.sig_len)); sig=sig.T.astype('float32');sig=(sig-sig.mean(1,keepdims=True))/(sig.std(1,keepdims=True)+1e-6); x=[];y=[]
    for i in range(0,sig.shape[1]-CTX-FUTURE,CTX): x.append(sig[:,i:i+CTX]);y.append(sig[:,i+CTX:i+CTX+FUTURE])
    return np.array(x),np.array(y)
def main(epochs=12):
    extended={'train':['slp01a','slp03','slp14'],'val':['slp02a'],'test':['slp04','slp16']}
    fast={'train':['slp01a'],'val':['slp02a'],'test':['slp02a']}
    splits=extended if all((RAW/f'{r}.dat').exists() for rs in extended.values() for r in rs) else fast
    print('Using', 'extended' if splits is extended else 'two-record fast prototype', 'forecast split')
    data={}
    for sp,rs in splits.items():
        a,b=zip(*(pair(r) for r in rs));x=np.concatenate(a);y=np.concatenate(b);data[sp]=DataLoader(TensorDataset(torch.tensor(x),torch.tensor(y)),16,shuffle=sp=='train');print(sp,x.shape)
    dev='cuda' if torch.cuda.is_available() else 'cpu';m=TwinForecaster(FUTURE).to(dev);opt=torch.optim.AdamW(m.parameters(),2e-4);loss=torch.nn.MSELoss();OUT.mkdir(parents=True,exist_ok=True);best=float('inf')
    for ep in range(epochs):
        m.train()
        for x,y in data['train']:opt.zero_grad();p,_=m(x.to(dev));l=loss(p,y.to(dev));l.backward();opt.step()
        m.eval();vals=[]
        with torch.no_grad():
            for x,y in data['val']:p,_=m(x.to(dev));vals.append(loss(p,y.to(dev)).item())
        v=float(np.mean(vals));print('epoch',ep+1,'val_mse',v)
        if v<best:best=v;torch.save({'state_dict':m.cpu().state_dict(),'model':'TwinForecaster','context':CTX,'future':FUTURE,'val_mse':v},OUT/'best_fp32.pth');m.to(dev)
    ck=torch.load(OUT/'best_fp32.pth',map_location=dev,weights_only=True);m.load_state_dict(ck['state_dict']);m.eval();truth=[];pred=[]
    with torch.no_grad():
        for x,y in data['test']:p,_=m(x.to(dev));truth.append(y.numpy());pred.append(p.cpu().numpy())
    y=np.concatenate(truth);p=np.concatenate(pred);metrics={}
    for i,n in enumerate(('ecg','eeg')):metrics[n]={'mae':float(mean_absolute_error(y[:,i].ravel(),p[:,i].ravel())),'rmse':float(mean_squared_error(y[:,i].ravel(),p[:,i].ravel())**.5),'r2':float(r2_score(y[:,i].ravel(),p[:,i].ravel()))}
    (OUT/'metrics.json').write_text(json.dumps(metrics,indent=2));print(json.dumps(metrics,indent=2))
if __name__=='__main__':main(int(sys.argv[1]) if len(sys.argv)>1 else 12)
