"""Download small public, record-level starter subsets for local CPU experiments."""
from __future__ import annotations
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]/'data'
SETS={'mitdb':{'records':['100','101','103','105','106','108','109','112','114','115'],'files':['dat','hea','atr']},'slpdb':{'records':['slp01a','slp02a','slp03','slp04','slp14','slp16'],'files':['dat','hea','ecg','st']}}
BASE='https://physionet.org/files/{db}/1.0.0/{record}.{ext}'
def download(db,record,ext):
    dest=ROOT/db/f'{record}.{ext}'; dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and dest.stat().st_size>0: print('kept',dest); return
    part=dest.with_suffix(dest.suffix+'.part'); start=part.stat().st_size if part.exists() else 0; print(f'downloading {dest.name} from byte {start}',flush=True)
    headers={'Range':f'bytes={start}-'} if start else {}; response=requests.get(BASE.format(db=db,record=record,ext=ext),headers=headers,stream=True,timeout=(15,90)); response.raise_for_status()
    if start and response.status_code!=206: start=0
    with part.open('ab' if start else 'wb') as f:
        for chunk in response.iter_content(1024*256):
            if chunk:f.write(chunk)
    part.replace(dest)
def main():
    for db,spec in SETS.items():
        for r in spec['records']:
            for ext in spec['files']: download(db,r,ext)
    print('Done. Starter files are intentionally small; use record-level test splits only.')
if __name__=='__main__': main()
