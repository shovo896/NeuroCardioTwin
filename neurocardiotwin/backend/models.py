"""Small CPU-friendly PyTorch models used by the NeuroCardioTwin research pipeline."""
from __future__ import annotations
import torch
from torch import nn

class Encoder(nn.Module):
    def __init__(self, channels: int = 1, width: int = 48):
        super().__init__()
        self.cnn = nn.Sequential(nn.Conv1d(channels,width,9,4,4),nn.GELU(),nn.Conv1d(width,width,7,4,3),nn.GELU())
        self.pos = nn.Parameter(torch.randn(1, 64, width) * .01)
        layer = nn.TransformerEncoderLayer(width, 4, 96, dropout=.1, batch_first=True, norm_first=True)
        self.blocks = nn.TransformerEncoder(layer, 2, enable_nested_tensor=False)
    def forward(self, x):
        z = self.cnn(x).transpose(1,2)
        return self.blocks(z + self.pos[:,:z.size(1)]).mean(1)

class SeizureClassifier(nn.Module):
    """Matches the seizure architecture in the supplied notebook."""
    def __init__(self): super().__init__(); self.enc=Encoder(1); self.head=nn.Linear(48,1)
    def forward(self,x): return self.head(self.enc(x)).squeeze(-1)

class ArrhythmiaClassifier(nn.Module):
    def __init__(self): super().__init__(); self.net=nn.Sequential(nn.Conv1d(1,24,9,2,4),nn.GELU(),nn.Conv1d(24,48,7,2,3),nn.GELU(),nn.AdaptiveAvgPool1d(1)); self.head=nn.Linear(48,1)
    def forward(self,x): return self.head(self.net(x).squeeze(-1)).squeeze(-1)

class TwinForecaster(nn.Module):
    """Joint ECG–EEG next-window forecaster; adaptive behaviour remains experimental."""
    def __init__(self, future: int=64):
        super().__init__(); self.future=future; self.ecg=Encoder(1); self.eeg=Encoder(1); self.quality=nn.Sequential(nn.Linear(4,16),nn.ReLU(),nn.Linear(16,2),nn.Sigmoid()); self.head=nn.Linear(96,2*future)
    def forward(self,x):
        stats=torch.stack((x.mean(-1),x.std(-1)),dim=-1).flatten(1); w=self.quality(stats)
        z=torch.cat((self.ecg(x[:,:1])*w[:,:1],self.eeg(x[:,1:2])*w[:,1:2]),-1)
        return self.head(z).view(-1,2,self.future),w
