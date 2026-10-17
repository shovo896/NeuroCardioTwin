from __future__ import annotations
import json,sys
from pathlib import Path
import numpy as np, torch
from torch.utils.data import DataLoader,TensorDataset
from sklearn.metrics import accuracy_score,precision_recall_fscore_support,roc_auc_score,average_precision_score
sys.path.insert(0,str(Path(__file__).resolve().parents[1])); from backend.models import SeizureClassifier
ROOT=Path(__file__).resolve().parents[1]; CACHE=ROOT.parent/'chb_cache.npz'; OUT=ROOT/'models'/'seizure'; torch.manual_seed(42); np.random.seed(42)
def loader(x,y,shuffle): return DataLoader(TensorDataset(torch.tensor(x,dtype=torch.float32),torch.tensor(y,dtype=torch.float32)),batch_size=32,shuffle=shuffle,num_workers=0)
def main(epochs=12):
    if not CACHE.exists(): raise FileNotFoundError(f'Missing supplied cache: {CACHE}')
    with np.load(CACHE,allow_pickle=False) as z: x=z['x'].astype('float32');y=z['y'].astype('float32');sp=z['split'].astype(str)
    norm=x.mean((1,2),keepdims=True); scale=x.std((1,2),keepdims=True)+1e-6; x=(x-norm)/scale
    d={s:loader(x[sp==s],y[sp==s],s=='train') for s in ('train','val','test')}; dev=torch.device('cuda' if torch.cuda.is_available() else 'cpu'); model=SeizureClassifier().to(dev); opt=torch.optim.AdamW(model.parameters(),lr=2e-4,weight_decay=1e-4); pos=torch.tensor([(y[sp=='train']==0).sum()/max((y[sp=='train']==1).sum(),1)],device=dev); loss_fn=torch.nn.BCEWithLogitsLoss(pos_weight=pos); best=-1; OUT.mkdir(parents=True,exist_ok=True)
    for epoch in range(1,epochs+1):
        model.train()
        for xb,yb in d['train']:
            opt.zero_grad(); loss=loss_fn(model(xb.to(dev)),yb.to(dev)); loss.backward(); opt.step()
        model.eval(); yy=[];pp=[]
        with torch.no_grad():
            for xb,yb in d['val']: yy.append(yb.numpy());pp.append(torch.sigmoid(model(xb.to(dev))).cpu().numpy())
        yy=np.concatenate(yy);pp=np.concatenate(pp); auc=roc_auc_score(yy,pp)
        print(f'epoch={epoch:02d} val_auroc={auc:.4f}',flush=True)
        if auc>best: best=auc; torch.save({'state_dict':model.cpu().state_dict(),'model':'SeizureClassifier','input_samples':512,'normalization':'per-window z-score','val_auroc':float(auc)},OUT/'best_fp32.pth'); model.to(dev)
    ck=torch.load(OUT/'best_fp32.pth',map_location=dev,weights_only=True);model.load_state_dict(ck['state_dict']);model.eval();yy=[];pp=[]
    with torch.no_grad():
        for xb,yb in d['test']: yy.append(yb.numpy());pp.append(torch.sigmoid(model(xb.to(dev))).cpu().numpy())
    yy=np.concatenate(yy);pp=np.concatenate(pp); pred=pp>=.5;p,r,f,_=precision_recall_fscore_support(yy,pred,average='binary',zero_division=0); metrics={'accuracy':float(accuracy_score(yy,pred)),'precision':float(p),'recall':float(r),'f1':float(f),'auroc':float(roc_auc_score(yy,pp)),'auprc':float(average_precision_score(yy,pp)),'split':'cache-provided test split','warning':'Starter research run only; do not use clinically.'}; (OUT/'metrics.json').write_text(json.dumps(metrics,indent=2));print(json.dumps(metrics,indent=2))
if __name__=='__main__': main(int(sys.argv[1]) if len(sys.argv)>1 else 12)
