import requests,math
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier,ExtraTreesClassifier
END=int(pd.Timestamp('2026-08-17',tz='UTC').timestamp());START=int(pd.Timestamp('2026-06-25',tz='UTC').timestamp())
def load(sym):
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={START}&period2={END}&interval=5m&events=history&includePrePost=true'
 r=requests.get(u,timeout=90,headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status();z=r.json()['chart']['result'][0];q=z['indicators']['quote'][0]
 return pd.DataFrame({'ts':pd.to_datetime(z['timestamp'],unit='s',utc=True),'open':q['open'],'high':q['high'],'low':q['low'],'close':q['close'],'volume':q.get('volume',[None]*len(z['timestamp']))}).dropna(subset=['open','high','low','close']).sort_values('ts').drop_duplicates('ts')
a=load('6E=F').rename(columns={c:f'a_{c}' for c in ['open','high','low','close','volume']});m=load('M6E=F').rename(columns={c:f'm_{c}' for c in ['open','high','low','close','volume']});df=m.merge(a,on='ts',how='inner');df=df[df.ts.dt.weekday<5].sort_values('ts').reset_index(drop=True);print('MATCH',len(df),df.ts.min(),df.ts.max())
# lead-lag diagnostic
df['ar']=np.log(df.a_close).diff();df['mr']=np.log(df.m_close).diff()
for lag in range(-3,4):
 x=df.ar;y=df.mr.shift(-lag);nz=(x!=0)&(y!=0);print('6E_CURRENT_vs_M6E_LAG',lag,'corr',x.corr(y),'sign',float((np.sign(x[nz])==np.sign(y[nz])).mean()),'n',int(nz.sum()))
# M6E current price features plus 6E source price/volume features.
def add(prefix):
 close=df[f'{prefix}_close'];high=df[f'{prefix}_high'];low=df[f'{prefix}_low'];op=df[f'{prefix}_open'];pc=close.shift();rng=high-low;tr=pd.concat([rng,(high-pc).abs(),(low-pc).abs()],axis=1).max(axis=1);atr=tr.rolling(48).mean();r=np.log(close).diff();df[f'{prefix}_r1']=r
 for n in [2,3,6,12,24,48,96,288]:df[f'{prefix}_r{n}']=np.log(close).diff(n)
 for n in [6,12,24,48,96]:
  ma=close.rolling(n).mean();sd=close.rolling(n).std();df[f'{prefix}_z{n}']=(close-ma)/sd;df[f'{prefix}_gap{n}']=close/ma-1
 df[f'{prefix}_range']=rng/atr;df[f'{prefix}_body']=(close-op)/atr;df[f'{prefix}_clv']=((close-low)-(high-close))/rng.replace(0,np.nan)
 v=pd.to_numeric(df[f'{prefix}_volume'],errors='coerce').fillna(0).clip(lower=0);lv=np.log1p(v);df[f'{prefix}_lv']=lv;df[f'{prefix}_vz48']=(lv-lv.rolling(48).mean())/lv.rolling(48).std();df[f'{prefix}_vchg']=lv-lv.shift()
add('a');add('m')
# Relative contract signals.
df['basis_am']=df.a_close-df.m_close;df['basis_chg']=df.basis_am.diff();df['ret_diff']=df.a_r1-df.m_r1;df['vol_ratio_contract']=df.a_vz48-df.m_vz48
# time
df['hour']=df.ts.dt.hour;df['minute']=df.ts.dt.minute;df['dow']=df.ts.dt.weekday;mins=df.hour*60+df.minute;df['sin_time']=np.sin(2*np.pi*mins/1440);df['cos_time']=np.cos(2*np.pi*mins/1440);df['london']=(df.hour.between(7,11)).astype(float);df['ny']=(df.hour.between(12,16)).astype(float);df['overlap']=(df.hour.between(12,15)).astype(float)
for h in [1,3,6,12]:df[f'fwd{h}']=np.log(df.m_close.shift(-h)/df.m_close);df[f'y{h}']=(df[f'fwd{h}']>0).astype(float);df.loc[df[f'fwd{h}'].isna(),f'y{h}']=np.nan
FEATURES=[c for c in df.columns if c.startswith(('a_r','a_z','a_gap','a_range','a_body','a_clv','a_lv','a_vz','a_vchg','m_r','m_z','m_gap','m_range','m_body','m_clv','m_lv','m_vz','m_vchg'))]+['basis_am','basis_chg','ret_diff','vol_ratio_contract','sin_time','cos_time','london','ny','overlap','dow'];df[FEATURES]=df[FEATURES].replace([np.inf,-np.inf],np.nan);print('FEATURES',len(FEATURES))
def models():return {'logit':Pipeline([('i',SimpleImputer(strategy='median')),('s',StandardScaler()),('x',LogisticRegression(C=.12,max_iter=1200))]),'hgb':Pipeline([('i',SimpleImputer(strategy='median')),('x',HistGradientBoostingClassifier(max_iter=90,learning_rate=.04,max_leaf_nodes=10,min_samples_leaf=100,l2_regularization=5,random_state=61))]),'extra':Pipeline([('i',SimpleImputer(strategy='median')),('x',ExtraTreesClassifier(n_estimators=250,max_depth=7,min_samples_leaf=50,max_features=.5,class_weight='balanced',n_jobs=-1,random_state=61))])}
def wilson(k,n,z=1.959963984540054):
 if n<=0:return np.nan,np.nan
 p=k/n;den=1+z*z/n;ctr=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;return ctr-half,ctr+half
start_test=pd.Timestamp('2026-07-27',tz='UTC');end_test=df.ts.max().floor('D')+pd.Timedelta(days=1);weeks=pd.date_range(start_test,end_test,freq='7D');rows=[]
for h in [1,3,6,12]:
 pieces=[];target=f'y{h}'
 for aa in weeks:
  b=min(aa+pd.Timedelta(days=7),end_test);tr=df[(df.ts<(aa-pd.Timedelta(minutes=5*h)))&df[target].notna()];te=df[(df.ts>=aa)&(df.ts<b)&df[target].notna()]
  if len(tr)<4500 or len(te)<100:continue
  P=[]
  for mod in models().values():mod.fit(tr[FEATURES],tr[target].astype(int));P.append(mod.predict_proba(te[FEATURES])[:,1])
  P=np.vstack(P);pieces.append(pd.DataFrame({'ts':te.ts.values,'y':te[target].astype(int).values,'p':P.mean(0),'spread':P.max(0)-P.min(0),'fwd':te[f'fwd{h}'].values}))
 if not pieces:continue
 pr=pd.concat(pieces,ignore_index=True).sort_values('ts').reset_index(drop=True)
 for t in [.525,.55,.575,.60,.625,.65,.675,.70,.725,.75,.775,.80]:
  for agree in [False,True]:
   use=(pr.p>=t)|(pr.p<=1-t)
   if agree:use&=pr.spread<=.10
   q=pr[use];n=len(q)
   if not n:continue
   pred=(q.p>=.5).astype(int);k=int((pred==q.y).sum());L,U=wilson(k,n);keep=[];last=None
   for idx,r in q.iterrows():
    tt=pd.Timestamp(r.ts)
    if last is None or tt-last>=pd.Timedelta(minutes=5*h):keep.append(idx);last=tt
   qs=q.loc[keep];ps=(qs.p>=.5).astype(int);ks=int((ps==qs.y).sum()) if len(qs) else 0;LS,US=wilson(ks,len(qs)) if len(qs) else (np.nan,np.nan);signed=np.where(pred==1,1,-1)*q.fwd;ss=np.where(ps==1,1,-1)*qs.fwd if len(qs) else np.array([])
   rows.append(dict(h=h,t=t,agree=agree,n=n,accuracy=k/n,wilson_lo=L,spaced_n=len(qs),spaced_acc=ks/len(qs) if len(qs) else np.nan,spaced_lo=LS,mean_signed=float(np.mean(signed)),spaced_mean=float(np.mean(ss)) if len(ss) else np.nan,coverage=n/len(pr)))
r=pd.DataFrame(rows);print('=== M6E TARGET ===');print(r.sort_values(['spaced_acc','spaced_n'],ascending=[False,False]).head(140).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),spaced_acc=lambda x:(100*x.spaced_acc).round(2),spaced_lo=lambda x:(100*x.spaced_lo).round(2),mean_signed=lambda x:(1e4*x.mean_signed).round(3),spaced_mean=lambda x:(1e4*x.spaced_mean).round(3),coverage=lambda x:(100*x.coverage).round(2)).to_string(index=False));print('75_RAW_N30',len(r[(r.accuracy>=.75)&(r.n>=30)]),'75_SPACED_N30',len(r[(r.spaced_acc>=.75)&(r.spaced_n>=30)]))
