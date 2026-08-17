import requests, math
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier,ExtraTreesClassifier

END=int(pd.Timestamp('2026-08-17',tz='UTC').timestamp()); START=int(pd.Timestamp('2026-06-25',tz='UTC').timestamp())
def load(sym):
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={START}&period2={END}&interval=5m&events=history&includePrePost=true'
 r=requests.get(u,timeout=90,headers={'User-Agent':'Mozilla/5.0'}); r.raise_for_status(); z=r.json()['chart']['result'][0]; q=z['indicators']['quote'][0]
 return pd.DataFrame({'ts':pd.to_datetime(z['timestamp'],unit='s',utc=True),'open':q['open'],'high':q['high'],'low':q['low'],'close':q['close'],'volume':q.get('volume',[None]*len(z['timestamp']))}).dropna(subset=['open','high','low','close']).sort_values('ts').drop_duplicates('ts')
a=load('6E=F').rename(columns={c:f'a_{c}' for c in ['open','high','low','close','volume']}); m=load('M6E=F').rename(columns={c:f'm_{c}' for c in ['open','high','low','close','volume']})
df=m.merge(a,on='ts',how='inner'); df=df[df.ts.dt.weekday<5].sort_values('ts').reset_index(drop=True)
print('MATCHED',len(df),df.ts.min(),df.ts.max())
# Diagnostics around M6E discreteness.
df['mr1']=df.m_close.diff(); df['ar1']=df.a_close.diff()
for h in [1,3,6,12]:
 d=df.m_close.shift(-h)-df.m_close
 print('M6E_FWD',h,'ZERO_PCT',100*(d.abs()<5e-8).mean(),'LT1TICK_PCT',100*(d.abs()<0.0001-1e-8).mean(),'GE1TICK_PCT',100*(d.abs()>=0.0001-1e-8).mean())
print('M6E unique increments sample',np.sort(np.unique(np.round(df.mr1.dropna().abs().to_numpy(),7)))[:20])

# Feature builder; all features known at completed current 5m bar.
def add(prefix):
 close=df[f'{prefix}_close']; high=df[f'{prefix}_high']; low=df[f'{prefix}_low']; op=df[f'{prefix}_open']; pc=close.shift(); rng=high-low; tr=pd.concat([rng,(high-pc).abs(),(low-pc).abs()],axis=1).max(axis=1); atr=tr.rolling(48).mean(); r=np.log(close).diff(); df[f'{prefix}_r1']=r
 for n in [2,3,6,12,24,48,96,288]: df[f'{prefix}_r{n}']=np.log(close).diff(n)
 for n in [6,12,24,48,96]:
  ma=close.rolling(n).mean(); sd=close.rolling(n).std(); df[f'{prefix}_z{n}']=(close-ma)/sd; df[f'{prefix}_gap{n}']=close/ma-1
 df[f'{prefix}_range']=rng/atr; df[f'{prefix}_body']=(close-op)/atr; df[f'{prefix}_clv']=((close-low)-(high-close))/rng.replace(0,np.nan); df[f'{prefix}_uw']=(high-df[[f'{prefix}_open',f'{prefix}_close']].max(axis=1))/atr; df[f'{prefix}_lw']=(df[[f'{prefix}_open',f'{prefix}_close']].min(axis=1)-low)/atr
 v=pd.to_numeric(df[f'{prefix}_volume'],errors='coerce').fillna(0).clip(lower=0); lv=np.log1p(v); df[f'{prefix}_lv']=lv; df[f'{prefix}_vz48']=(lv-lv.rolling(48).mean())/lv.rolling(48).std(); df[f'{prefix}_vchg']=lv-lv.shift()
add('a'); add('m')
df['basis']=df.a_close-df.m_close; df['basis_chg']=df.basis.diff(); df['ret_diff']=df.a_r1-df.m_r1; df['vol_rel']=df.a_vz48-df.m_vz48
df['hour']=df.ts.dt.hour; df['minute']=df.ts.dt.minute; df['dow']=df.ts.dt.weekday; mins=df.hour*60+df.minute; df['sin_time']=np.sin(2*np.pi*mins/1440); df['cos_time']=np.cos(2*np.pi*mins/1440); df['london']=(df.hour.between(7,11)).astype(float); df['ny']=(df.hour.between(12,16)).astype(float); df['overlap']=(df.hour.between(12,15)).astype(float)
FEATURES=[c for c in df.columns if c.startswith(('a_r','a_z','a_gap','a_range','a_body','a_clv','a_uw','a_lw','a_lv','a_vz','a_vchg','m_r','m_z','m_gap','m_range','m_body','m_clv','m_uw','m_lw','m_lv','m_vz','m_vchg'))]+['basis','basis_chg','ret_diff','vol_rel','sin_time','cos_time','london','ny','overlap','dow']
df[FEATURES]=df[FEATURES].replace([np.inf,-np.inf],np.nan)

def models(seed=71): return {
 'logit':Pipeline([('i',SimpleImputer(strategy='median')),('s',StandardScaler()),('x',LogisticRegression(C=.12,max_iter=1200))]),
 'hgb':Pipeline([('i',SimpleImputer(strategy='median')),('x',HistGradientBoostingClassifier(max_iter=90,learning_rate=.04,max_leaf_nodes=10,min_samples_leaf=100,l2_regularization=5,random_state=seed))]),
 'extra':Pipeline([('i',SimpleImputer(strategy='median')),('x',ExtraTreesClassifier(n_estimators=250,max_depth=7,min_samples_leaf=50,max_features=.5,class_weight='balanced',n_jobs=-1,random_state=seed))])}
def wilson(k,n,z=1.959963984540054):
 if n<=0:return np.nan,np.nan
 p=k/n; den=1+z*z/n; ctr=(p+z*z/(2*n))/den; half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den; return ctr-half,ctr+half

def fit_predict(train,test,target,seed=71):
 P=[]
 for mod in models(seed).values(): mod.fit(train[FEATURES],train[target].astype(int)); P.append(mod.predict_proba(test[FEATURES])[:,1])
 P=np.vstack(P); return P.mean(0),P.max(0)-P.min(0)

# ------------------------------------------------------------------
# 1) Tick-threshold directional labels: discard moves smaller than N ticks.
# M6E tick = 0.0001. Target uses future close h bars later.
# Final week is LOCKED holdout. Threshold t selected only on Jul27-Aug07 validation.
# ------------------------------------------------------------------
TRAIN_END=pd.Timestamp('2026-07-27',tz='UTC'); VAL_END=pd.Timestamp('2026-08-10',tz='UTC'); HOLD_END=pd.Timestamp('2026-08-15',tz='UTC')
print('\n=== TICK-THRESHOLD LOCKED HOLDOUT ===')
rows=[]
for h in [1,3,6,12]:
 for ticks in [1,2,3]:
  move=df.m_close.shift(-h)-df.m_close; valid=move.abs()>=(ticks*0.0001-1e-8); target=f'y_thr_{h}_{ticks}'; df[target]=np.nan; df.loc[valid,target]=(move[valid]>0).astype(int)
  tr=df[(df.ts<(TRAIN_END-pd.Timedelta(minutes=5*h)))&df[target].notna()]; va=df[(df.ts>=TRAIN_END)&(df.ts<VAL_END)&df[target].notna()]; ho=df[(df.ts>=VAL_END)&(df.ts<HOLD_END)&df[target].notna()]
  if len(tr)<4000 or len(va)<20 or len(ho)<10: continue
  pv,sv=fit_predict(tr,va,target,73); vv=va[['ts',target]].copy(); vv['p']=pv; vv['spread']=sv
  # Select t on validation by Wilson lower bound, requiring at least 30 validation signals when possible.
  choices=[]
  for t in [.525,.55,.575,.60,.625,.65,.675,.70,.725,.75,.775,.80]:
   for agree in [False,True]:
    use=(vv.p>=t)|(vv.p<=1-t)
    if agree:use&=vv.spread<=.10
    q=vv[use]; n=len(q)
    if n<20:continue
    k=int((((q.p>=.5).astype(int))==q[target].astype(int)).sum()); L,U=wilson(k,n); choices.append((L,k/n,n,t,agree))
  if not choices:continue
  choices.sort(reverse=True); best=choices[0]; _,vacc,vn,t,agree=best
  # Refit on everything before locked holdout, with label purge.
  tr2=df[(df.ts<(VAL_END-pd.Timedelta(minutes=5*h)))&df[target].notna()]; ph,sh=fit_predict(tr2,ho,target,79); hh=ho[['ts',target]].copy(); hh['p']=ph;hh['spread']=sh
  use=(hh.p>=t)|(hh.p<=1-t)
  if agree:use&=hh.spread<=.10
  q=hh[use].copy(); n=len(q)
  if n:
   pred=(q.p>=.5).astype(int);k=int((pred==q[target].astype(int)).sum());L,U=wilson(k,n);signed=np.where(pred==1,1,-1)*(df.loc[q.index].m_close.shift(-h) if False else 0)
   rows.append(dict(h=h,ticks=ticks,val_n=vn,val_acc=vacc,t=t,agree=agree,hold_n=n,hold_acc=k/n,hold_lo=L,hold_class_up=float(q[target].mean())))
R=pd.DataFrame(rows);print(R.sort_values(['hold_acc','hold_n'],ascending=[False,False]).assign(val_acc=lambda x:(100*x.val_acc).round(2),hold_acc=lambda x:(100*x.hold_acc).round(2),hold_lo=lambda x:(100*x.hold_lo).round(2)).to_string(index=False))

# ------------------------------------------------------------------
# 2) First-hit barriers on M6E using 5m high/low. Discard same-bar ambiguous hits.
# Labels: which +/- N tick barrier hits first within horizon.
# ------------------------------------------------------------------
def barrier_label(ticks,hbars):
 dist=ticks*0.0001; y=np.full(len(df),np.nan); hitbars=np.full(len(df),np.nan); C=df.m_close.to_numpy(); H=df.m_high.to_numpy(); L=df.m_low.to_numpy()
 for i in range(len(df)-1):
  up=C[i]+dist;dn=C[i]-dist
  for j in range(i+1,min(len(df),i+1+hbars)):
   hu=H[j]>=up;ld=L[j]<=dn
   if hu and ld: break
   if hu:y[i]=1;hitbars[i]=j-i;break
   if ld:y[i]=0;hitbars[i]=j-i;break
 return y,hitbars
print('\n=== M6E FIRST-HIT BARRIER LOCKED HOLDOUT ===')
brows=[]
for ticks in [1,2,3,5]:
 for hb in [3,6,12,24]:
  y,hits=barrier_label(ticks,hb); target=f'y_bar_{ticks}_{hb}';df[target]=y
  tr=df[(df.ts<(TRAIN_END-pd.Timedelta(minutes=5*hb)))&df[target].notna()];va=df[(df.ts>=TRAIN_END)&(df.ts<VAL_END)&df[target].notna()];ho=df[(df.ts>=VAL_END)&(df.ts<HOLD_END)&df[target].notna()]
  if len(tr)<3000 or len(va)<30 or len(ho)<15:continue
  pv,sv=fit_predict(tr,va,target,83);vv=va[['ts',target]].copy();vv['p']=pv;vv['spread']=sv;choices=[]
  for t in [.525,.55,.575,.60,.625,.65,.675,.70,.725,.75,.775,.80]:
   for agree in [False,True]:
    use=(vv.p>=t)|(vv.p<=1-t)
    if agree:use&=vv.spread<=.10
    q=vv[use];n=len(q)
    if n<25:continue
    k=int((((q.p>=.5).astype(int))==q[target].astype(int)).sum());L,U=wilson(k,n);choices.append((L,k/n,n,t,agree))
  if not choices:continue
  choices.sort(reverse=True);_,vacc,vn,t,agree=choices[0]
  tr2=df[(df.ts<(VAL_END-pd.Timedelta(minutes=5*hb)))&df[target].notna()];ph,sh=fit_predict(tr2,ho,target,89);hh=ho[['ts',target]].copy();hh['p']=ph;hh['spread']=sh;use=(hh.p>=t)|(hh.p<=1-t)
  if agree:use&=hh.spread<=.10
  q=hh[use];n=len(q)
  if n:
   k=int((((q.p>=.5).astype(int))==q[target].astype(int)).sum());L,U=wilson(k,n);brows.append(dict(ticks=ticks,hbars=hb,val_n=vn,val_acc=vacc,t=t,agree=agree,hold_n=n,hold_acc=k/n,hold_lo=L,hold_up_rate=float(q[target].mean())))
B=pd.DataFrame(brows);print(B.sort_values(['hold_acc','hold_n'],ascending=[False,False]).assign(val_acc=lambda x:(100*x.val_acc).round(2),hold_acc=lambda x:(100*x.hold_acc).round(2),hold_lo=lambda x:(100*x.hold_lo).round(2)).to_string(index=False))
print('\n=== ROBUST HOLDOUT 75 CHECK ===')
print('threshold candidates hold_n>=30',len(R[(R.hold_acc>=.75)&(R.hold_n>=30)]) if len(R) else 0,'barrier candidates hold_n>=30',len(B[(B.hold_acc>=.75)&(B.hold_n>=30)]) if len(B) else 0)
if len(R):print('THR75\n',R[(R.hold_acc>=.75)&(R.hold_n>=30)].to_string(index=False))
if len(B):print('BAR75\n',B[(B.hold_acc>=.75)&(B.hold_n>=30)].to_string(index=False))
