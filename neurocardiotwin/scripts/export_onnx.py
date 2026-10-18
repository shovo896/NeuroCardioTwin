"""Export local PyTorch checkpoints to portable ONNX models for Vercel inference."""
from pathlib import Path
import sys,torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));from backend.models import SeizureClassifier,ArrhythmiaClassifier,TwinForecaster
class ForecastOnly(torch.nn.Module):
    def __init__(self,m):super().__init__();self.m=m
    def forward(self,x):return self.m(x)[0]
def export(task,cls,shape):
    p=ROOT/'models'/task/'best_fp32.pth';m=cls().eval();m.load_state_dict(torch.load(p,map_location='cpu',weights_only=True)['state_dict']);
    if task=='forecast':m=ForecastOnly(m)
    x=torch.zeros(*shape);out=p.with_suffix('.onnx');torch.onnx.export(m,x,str(out),input_names=['signal'],output_names=['prediction'],opset_version=17);print(out,out.stat().st_size)
for task,cls,shape in [('seizure',SeizureClassifier,(1,1,512)),('arrhythmia',ArrhythmiaClassifier,(1,1,180)),('forecast',TwinForecaster,(1,2,256))]:export(task,cls,shape)
