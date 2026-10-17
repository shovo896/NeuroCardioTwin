"""Download small public, record-level starter subsets for local CPU experiments."""
from __future__ import annotations
from pathlib import Path
from urllib.request import urlretrieve

ROOT=Path(__file__).resolve().parents[1]/'data'
SETS={'mitdb':{'records':['100','101','103','105'],'files':['dat','hea','atr']},'slpdb':{'records':['slp01a','slp02a','slp03'],'files':['dat','hea','ecg','st']}}
BASE='https://physionet.org/files/{db}/1.0.0/{record}.{ext}'
def download(db,record,ext):
    dest=ROOT/db/f'{record}.{ext}'; dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and dest.stat().st_size>0: print('kept',dest); return
    part=dest.with_suffix(dest.suffix+'.part'); print('downloading',dest.name,flush=True)
    urlretrieve(BASE.format(db=db,record=record,ext=ext),part); part.replace(dest)
def main():
    for db,spec in SETS.items():
        for r in spec['records']:
            for ext in spec['files']: download(db,r,ext)
    print('Done. Starter files are intentionally small; use record-level test splits only.')
if __name__=='__main__': main()
