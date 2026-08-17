import requests, math
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier, ExtraTreesClassifier

START=int(pd.Timestamp('2024-08-01',tz='UTC').timestamp()); END=int(pd.Timestamp('2026-08-17',tz='UTC').timestamp())
SYMS={'eur':'EURUSD=X','dxy':'DX=F','zt':'ZT=F','oil':'CL=F','gold':'GC=F','es':'ES=F'}
def load(sym):
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={START}&period2={END}&interval=1h&events=history&includePrePost=true'
 r=requests.get(u,timeout=90,headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status();z=r.json()['chart']['result'][0];q=z['indicators']['quote'][0]
 return pd.DataFrame({'ts':pd.to_datetime(z['timestamp'],unit='s',utc=True),'close':q['close'],'open':q['open'],'high':q['high'],'low':q['low']}).dropna().sort_values('ts').drop_duplicates('ts')
D={}
for k,s in SYMS.items():
 try:D[k]=load(s);print(k,len(D[k]),D[k].ts.min(),D[k].ts.max())
 except Exception as e:print('FAIL',k,s,repr(e))
if 'eur' not in D:raise RuntimeError('no EUR hourly')
# Base on EUR bars; merge most recent exact hourly close for cross assets.
e=D['eur'].copy().rename(columns={c:f'eur_{c}' for c in ['close','open','high','low']})
e=e[e.ts.dt.weekday<5].copy()
for k,z in D.items():
 if k=='eur':continue
 z=z[['ts','close']].rename(columns={'close':f'{k}_close'})
 e=e.merge(z,on='ts',how='left')
e=e.sort_values('ts').reset_index(drop=True)
# forward fill only within 3 rows to handle exchange hour mismatch; never backward-fill future.
cross=[c for c in e.columns if c.endswith('_close') and not c.startswith('eur_')]
e[cross]=e[cross].ffill(limit=3)

# EUR features.
e['eur_ret1']=np.log(e.eur_close).diff();rng=e.eur_high-e.eur_low;pc=e.eur_close.shift();tr=pd.concat([rng,(e.eur_high-pc).abs(),(e.eur_low-pc).abs()],axis=1).max(axis=1);atr=tr.rolling(24).mean()
e['eur_body']=(e.eur_close-e.eur_open)/atr;e['eur_range']=rng/atr;e['eur_clv']=((e.eur_close-e.eur_low)-(e.eur_high-e.eur_close))/rng.replace(0,np.nan)
for n in [2,3,6,12,24,48]:e[f'eur_ret{n}']=np.log(e.eur_close).diff(n)
# cross returns and relative shocks.
for k in ['dxy','zt','oil','gold','es']:
 c=f'{k}_close'
 if c not in e:continue
 for n in [1,2,3,6,12,24]:e[f'{k}_ret{n}']=np.log(e[c]).diff(n)
# Lead-lag residual-esque combinations. Higher ZT = lower US2Y yields; lower DXY = EUR-positive.
if 'dxy_ret1' in e:
 e['eur_plus_dxy1']=e.eur_ret1+e.dxy_ret1;e['eur_plus_dxy3']=e.eur_ret3+e.dxy_ret3
if 'zt_ret1' in e:
 e['eur_minus_zt1']=e.eur_ret1-e.zt_ret1;e['eur_minus_zt3']=e.eur_ret3-e.zt_ret3
if 'dxy_ret1' in e and 'zt_ret1' in e:
 e['macro_impulse1']=-e.dxy_ret1+e.zt_ret1;e['macro_impulse3']=-e.dxy_ret3+e.zt_ret3;e['eur_vs_macro1']=e.eur_ret1-e.macro_impulse1;e['eur_vs_macro3']=e.eur_ret3-e.macro_impulse3
# time/session
e['hour']=e.ts.dt.hour;e['dow']=e.ts.dt.weekday;e['sin_hour']=np.sin(2*np.pi*e.hour/24);e['cos_hour']=np.cos(2*np.pi*e.hour/24);e['london']=(e.hour.between(7,11)).astype(float);e['ny']=(e.hour.between(12,16)).astype(float);e['overlap']=(e.hour.between(12,15)).astype(float)
# vol
e['vol6']=e.eur_ret1.rolling(6).std();e['vol24']=e.eur_ret1.rolling(24).std();e['volratio']=e.vol6/e.vol24
for h in [1,2,3,6]:
 e[f'fret{h}']=np.log(e.eur_close.shift(-h)/e.eur_close);e[f'y{h}']=(e[f'fret{h}']>0).astype(float);e.loc[e[f'fret{h}'].isna(),f'y{h}']=np.nan

FEATURES=[c for c in e.columns if any(c.startswith(p) for p in ['eur_ret','dxy_ret','zt_ret','oil_ret','gold_ret','es_ret'])]+['eur_body','eur_range','eur_clv','vol6','vol24','volratio','sin_hour','cos_hour','london','ny','overlap']
for c in ['eur_plus_dxy1','eur_plus_dxy3','eur_minus_zt1','eur_minus_zt3','macro_impulse1','macro_impulse3','eur_vs_macro1','eur_vs_macro3']:
 if c in e:FEATURES.append(c)
FEATURES=list(dict.fromkeys(FEATURES));print('FEATURES',len(FEATURES),FEATURES)

def models():return {
 'logit':Pipeline([('i',SimpleImputer(strategy='median')),('s',StandardScaler()),('m',LogisticRegression(C=.15,max_iter=1500))]),
 'hgb':Pipeline([('i',SimpleImputer(strategy='median')),('m',HistGradientBoostingClassifier(max_iter=100,learning_rate=.04,max_leaf_nodes=10,min_samples_leaf=60,l2_regularization=4,random_state=17))]),
 'extra':Pipeline([('i',SimpleImputer(strategy='median')),('m',ExtraTreesClassifier(n_estimators=300,max_depth=7,min_samples_leaf=35,max_features=.55,class_weight='balanced',n_jobs=-1,random_state=17))])}
def wilson(k,n,z=1.959963984540054):
 if n<=0:return np.nan,np.nan
 p=k/n;den=1+z*z/n;ctr=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;return ctr-half,ctr+half

# Quarterly expanding walkforward.
quarters=pd.period_range('2025Q2','2026Q3',freq='Q');preds={}
for h in [1,2,3,6]:
 pieces=[];target=f'y{h}'
 for per in quarters:
  a=per.start_time.tz_localize('UTC');b=(per+1).start_time.tz_localize('UTC');trn=e[(e.ts<a)&e[target].notna()];tst=e[(e.ts>=a)&(e.ts<b)&e[target].notna()]
  if len(trn)<3000 or len(tst)<100:continue
  P=[]
  for m in models().values():m.fit(trn[FEATURES],trn[target].astype(int));P.append(m.predict_proba(tst[FEATURES])[:,1])
  P=np.vstack(P);p=P.mean(0);spread=P.max(0)-P.min(0);pieces.append(pd.DataFrame({'ts':tst.ts.values,'y':tst[target].astype(int).values,'p':p,'spread':spread,'p0':P[0],'p1':P[1],'p2':P[2]}))
 preds[h]=pd.concat(pieces,ignore_index=True) if pieces else pd.DataFrame()
print('=== CROSS ASSET SELECTIVE ===')
rows=[]
for h,pr in preds.items():
 if not len(pr):continue
 for t in [.525,.55,.575,.60,.625,.65,.675,.70,.725,.75,.775,.80]:
  for agree in [False,True]:
   use=(pr.p>=t)|(pr.p<=1-t)
   if agree:use&=pr.spread<=.10
   q=pr[use];n=len(q)
   if not n:continue
   k=int((((q.p>=.5).astype(int))==q.y).sum());L,U=wilson(k,n);recent=q[pd.to_datetime(q.ts)>=pd.Timestamp('2026-01-01')];kr=int((((recent.p>=.5).astype(int))==recent.y).sum()) if len(recent) else 0;LR,UR=wilson(kr,len(recent)) if len(recent) else (np.nan,np.nan)
   rows.append(dict(h=h,t=t,agree=agree,n=n,accuracy=k/n,wilson_lo=L,coverage=n/len(pr),recent_n=len(recent),recent_acc=kr/len(recent) if len(recent) else np.nan,recent_lo=LR))
r=pd.DataFrame(rows);print(r.sort_values(['accuracy','n'],ascending=[False,False]).head(120).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),coverage=lambda x:(100*x.coverage).round(2),recent_acc=lambda x:(100*x.recent_acc).round(2),recent_lo=lambda x:(100*x.recent_lo).round(2)).to_string(index=False))

# Locked 2026 rules based on extreme cross-asset disagreement thresholds from 2024-25 training.
tr=e[e.ts<pd.Timestamp('2026-01-01',tz='UTC')];ho=e[e.ts>=pd.Timestamp('2026-01-01',tz='UTC')]
def quant(f,q):return float(tr[f].quantile(q))
patterns={}
 'dxy_big_down_eur_notup': lambda z:(z.dxy_ret1<=quant('dxy_ret1',.1))&(z.eur_ret1<=0),
 'dxy_big_up_eur_notdn': lambda z:(z.dxy_ret1>=quant('dxy_ret1',.9))&(z.eur_ret1>=0),
 'zt_big_up_eur_notup': lambda z:(z.zt_ret1>=quant('zt_ret1',.9))&(z.eur_ret1<=0) if 'zt_ret1'in z else pd.Series(False,index=z.index),
 'zt_big_dn_eur_notdn': lambda z:(z.zt_ret1<=quant('zt_ret1',.1))&(z.eur_ret1>=0) if 'zt_ret1'in z else pd.Series(False,index=z.index),
 'macro_bull_eur_lag': lambda z:(z.macro_impulse1>=quant('macro_impulse1',.9))&(z.eur_ret1<=0) if 'macro_impulse1'in z else pd.Series(False,index=z.index),
 'macro_bear_eur_lag': lambda z:(z.macro_impulse1<=quant('macro_impulse1',.1))&(z.eur_ret1>=0) if 'macro_impulse1'in z else pd.Series(False,index=z.index),
 'dxy_dn_zt_up':lambda z:(z.dxy_ret1<=quant('dxy_ret1',.2))&(z.zt_ret1>=quant('zt_ret1',.8)) if 'zt_ret1'in z else pd.Series(False,index=z.index),
 'dxy_up_zt_dn':lambda z:(z.dxy_ret1>=quant('dxy_ret1',.8))&(z.zt_ret1<=quant('zt_ret1',.2)) if 'zt_ret1'in z else pd.Series(False,index=z.index),
}
print('\n=== LOCKED 2026 CROSS-ASSET PATTERNS ===')
rr=[]
for name,fn in patterns.items():
 mt=fn(tr).fillna(False);mh=fn(ho).fillna(False)
 for h in [1,2,3,6]:
  st=tr.loc[mt,f'fret{h}'].dropna();ntr=len(st)
  if ntr<50:continue
  up=float((st>0).mean());d=1 if up>=.5 else 0;tracc=max(up,1-up);sh=ho.loc[mh,f'fret{h}'].dropna();n=len(sh)
  if n<15:continue
  k=int((sh>0).sum()) if d else int((sh<0).sum());acc=k/n;L,U=wilson(k,n)
  rr.append(dict(pattern=name,h=h,train_n=ntr,train_acc=tracc,dir='UP' if d else 'DOWN',n=n,hold_acc=acc,wilson_lo=L,median=float(sh.median())))
rr=pd.DataFrame(rr);print(rr.sort_values(['hold_acc','n'],ascending=[False,False]).head(80).assign(train_acc=lambda x:(100*x.train_acc).round(2),hold_acc=lambda x:(100*x.hold_acc).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),median=lambda x:(100*x['median']).round(3)).to_string(index=False))
print('\n=== CROSS ASSET 75 N>=30 CHECK ===');print('model',len(r[(r.accuracy>=.75)&(r.n>=30)]),'locked',len(rr[(rr.hold_acc>=.75)&(rr.n>=30)]))
