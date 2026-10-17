from __future__ import annotations
import json,sys
from pathlib import Path
import numpy as np,torch,wfdb
from torch.utils.data import DataLoader,TensorDataset
from sklearn.metrics import accuracy_score,precision_recall_fscore_support,roc_auc_score
sys.path.insert(0,str(Path(__file__).resolve().parents[1])); from backend.models import ArrhythmiaClassifier
ROOT=Path(__file__).resolve().parents[1]; RAW=ROOT/'data'/'mitdb'; OUT=ROOT/'models'/'arrhythmia'; NORMAL={'N','L','R','e','j'}; ABNORMAL={'A','a','J','S','V','F','E','!'}
def windows(record):
    sig,_=wfdb.rdsamp(str(RAW/record),channels=[0]); ann=wfdb.rdann(str(RAW/record),'atr'); rows=[]
    for at,s in zip(ann.sample,ann.symbol):
        if s not in NORMAL|ABNORMAL or at<90 or at+90>=len(sig):continue
        x=sig[at-90:at+90,0].astype('float32');x=(x-x.mean())/(x.std()+1e-6);rows.append((x,s not in NORMAL))
    return rows
def main(epochs=12):
    splits={'train':['100','101'],'val':['103'],'test':['105']}; data={}
    for sp,rs in splits.items():
        rows=sum((windows(r) for r in rs),[]); x=np.array([a for a,_ in rows])[:,None,:];y=np.array([b for _,b in rows],dtype='float32');data[sp]=DataLoader(TensorDataset(torch.tensor(x),torch.tensor(y)),32,shuffle=sp=='train');print(sp,len(y),int(y.sum()))
    dev='cuda' if torch.cuda.is_available() else 'cpu';m=ArrhythmiaClassifier().to(dev);opt=torch.optim.AdamW(m.parameters(),2e-4);loss=torch.nn.BCEWithLogitsLoss();OUT.mkdir(parents=True,exist_ok=True);best=-1
    for ep in range(epochs):
        m.train()
        for x,y in data['train']:opt.zero_grad();l=loss(m(x.to(dev)),y.to(dev));l.backward();opt.step()
        m.eval();y=[];p=[]
        with torch.no_grad():
            for x,t in data['val']: y.append(t.numpy());p.append(torch.sigmoid(m(x.to(dev))).cpu().numpy())
        auc=roc_auc_score(np.concatenate(y),np.concatenate(p));print('epoch',ep+1,'val_auroc',auc)
        if auc>best:best=auc;torch.save({'state_dict':m.cpu().state_dict(),'model':'ArrhythmiaClassifier','input_samples':180,'sampling_rate':360,'val_auroc':float(auc)},OUT/'best_fp32.pth');m.to(dev)
if __name__=='__main__':main(int(sys.argv[1]) if len(sys.argv)>1 else 12)
