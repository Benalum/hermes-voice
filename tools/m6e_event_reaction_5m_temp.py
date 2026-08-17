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
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={START}&period2={END}&interval=5m&events=history&includePrePost=true';r=requests.get(u,timeout=90,headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status();z=r.json()['chart']['result'][0];q=z['indicators']['quote'][0]
 return pd.DataFrame({'ts':pd.to_datetime(z['timestamp'],unit='s',utc=True),'open':q['open'],'high':q['high'],'low':q['low'],'close':q['close'],'volume':q.get('volume',[None]*len(z['timestamp']))}).dropna(subset=['open','high','low','close']).sort_values('ts').drop_duplicates('ts')
a=load('6E=F').rename(columns={c:f'a_{c}' for c in ['open','high','low','close','volume']});m=load('M6E=F').rename(columns={c:f'm_{c}' for c in ['open','high','low','close','volume']});df=m.merge(a,on='ts',how='inner');df=df[df.ts.dt.weekday<5].sort_values('ts').reset_index(drop=True)
# During US daylight time, 8:30 ET=12:30 UTC and 10:00 ET=14:00 UTC. We enter only AFTER this 5m bar completes.
df['event830']=(df.ts.dt.hour==12)&(df.ts.dt.minute==30);df['event1000']=(df.ts.dt.hour==14)&(df.ts.dt.minute==0);df['event']=df.event830|df.event1000
# completed bar / history features
for p in ['a','m']:
 c=df[f'{p}_close'];o=df[f'{p}_open'];h=df[f'{p}_high'];l=df[f'{p}_low'];rng=h-l;pc=c.shift();tr=pd.concat([rng,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1);atr=tr.rolling(288).mean();df[f'{p}_r1']=np.log(c).diff();
 for n in [3,6,12,24,48,288]:df[f'{p}_r{n}']=np.log(c).diff(n)
 df[f'{p}_rangez']=(rng-rng.rolling(288).mean())/rng.rolling(288).std();df[f'{p}_bodyatr']=(c-o)/atr;df[f'{p}_clv']=((c-l)-(h-c))/rng.replace(0,np.nan)
 v=np.log1p(pd.to_numeric(df[f'{p}_volume'],errors='coerce').fillna(0).clip(lower=0));df[f'{p}_volz']=(v-v.rolling(288).mean())/v.rolling(288).std()
df['basis']=df.a_close-df.m_close;df['basis_chg']=df.basis.diff();df['ret_diff']=df.a_r1-df.m_r1;df['vol_diff']=df.a_volz-df.m_volz
# target close direction and barriers after reaction bar
for hb in [1,3,6,12]:df[f'fwd{hb}']=df.m_close.shift(-hb)-df.m_close;df[f'y{hb}']=np.where(df[f'fwd{hb}'].abs()>=.0001-1e-8,(df[f'fwd{hb}']>0).astype(float),np.nan)
def barrier(ticks,hb):
 dist=ticks*.0001;y=np.full(len(df),np.nan);C=df.m_close.to_numpy();H=df.m_high.to_numpy();L=df.m_low.to_numpy()
 for i in range(len(df)-1):
  up=C[i]+dist;dn=C[i]-dist
  for j in range(i+1,min(len(df),i+1+hb)):
   hu=H[j]>=up;ld=L[j]<=dn
   if hu and ld:break
   if hu:y[i]=1;break
   if ld:y[i]=0;break
 return y
for ticks in [1,2,3]:
 for hb in [3,6,12]:df[f'b{ticks}_{hb}']=barrier(ticks,hb)
FEATURES=['a_r1','a_r3','a_r6','a_r12','a_r24','a_r48','a_r288','m_r1','m_r3','m_r6','m_r12','m_r24','m_r48','m_r288','a_rangez','a_bodyatr','a_clv','a_volz','m_rangez','m_bodyatr','m_clv','m_volz','basis','basis_chg','ret_diff','vol_diff','event830','event1000'];df[FEATURES]=df[FEATURES].replace([np.inf,-np.inf],np.nan)
def models(seed=101):return {'l':Pipeline([('i',SimpleImputer(strategy='median')),('s',StandardScaler()),('x',LogisticRegression(C=.15,max_iter=1200))]),'h':Pipeline([('i',SimpleImputer(strategy='median')),('x',HistGradientBoostingClassifier(max_iter=80,learning_rate=.04,max_leaf_nodes=8,min_samples_leaf=20,l2_regularization=5,random_state=seed))]),'e':Pipeline([('i',SimpleImputer(strategy='median')),('x',ExtraTreesClassifier(n_estimators=250,max_depth=5,min_samples_leaf=10,max_features=.6,class_weight='balanced',n_jobs=-1,random_state=seed))])}
def wilson(k,n,z=1.959963984540054):
 if n<=0:return np.nan,np.nan
 p=k/n;den=1+z*z/n;ctr=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;return ctr-half,ctr+half
def fp(tr,te,target,seed):
 P=[]
 for x in models(seed).values():x.fit(tr[FEATURES],tr[target].astype(int));P.append(x.predict_proba(te[FEATURES])[:,1])
 P=np.vstack(P);return P.mean(0),P.max(0)-P.min(0)
# Locked split: develop threshold on Jul21-Aug2, final holdout Aug3-Aug14. Training only pre Jul21.
T0=pd.Timestamp('2026-07-21',tz='UTC');T1=pd.Timestamp('2026-08-03',tz='UTC');T2=pd.Timestamp('2026-08-15',tz='UTC')
print('EVENT_BARS',int(df.event.sum()),df.loc[df.event,'ts'].min(),df.loc[df.event,'ts'].max())
rows=[]
targets=[f'y{h}' for h in [1,3,6,12]]+[f'b{t}_{h}' for t in [1,2,3] for h in [3,6,12]]
for target in targets:
 horizon=12
 tr=df[(df.ts<T0-pd.Timedelta(hours=1))&df.event&df[target].notna()];va=df[(df.ts>=T0)&(df.ts<T1)&df.event&df[target].notna()];ho=df[(df.ts>=T1)&(df.ts<T2)&df.event&df[target].notna()]
 if len(tr)<25 or len(va)<8 or len(ho)<8:continue
 pv,sv=fp(tr,va,target,103);vv=va[['ts',target]].copy();vv['p']=pv;vv['s']=sv;choices=[]
 for t in [.50,.525,.55,.575,.60,.625,.65,.675,.70,.725,.75]:
  for ag in [False,True]:
   use=(vv.p>=t)|(vv.p<=1-t)
   if ag:use&=vv.s<=.12
   q=vv[use];n=len(q)
   if n<6:continue
   k=int((((q.p>=.5).astype(int))==q[target].astype(int)).sum());L,U=wilson(k,n);choices.append((L,k/n,n,t,ag))
 if not choices:continue
 choices.sort(reverse=True);_,vacc,vn,t,ag=choices[0];tr2=df[(df.ts<T1-pd.Timedelta(hours=1))&df.event&df[target].notna()];ph,sh=fp(tr2,ho,target,107);hh=ho[['ts',target]].copy();hh['p']=ph;hh['s']=sh;use=(hh.p>=t)|(hh.p<=1-t)
 if ag:use&=hh.s<=.12
 q=hh[use];n=len(q)
 if n:
  k=int((((q.p>=.5).astype(int))==q[target].astype(int)).sum());L,U=wilson(k,n);rows.append(dict(target=target,train_n=len(tr),val_n=vn,val_acc=vacc,t=t,agree=ag,hold_n=n,hold_acc=k/n,hold_lo=L,hold_up=float(q[target].mean())))
r=pd.DataFrame(rows);print('=== EVENT LOCKED HOLDOUT ===');print(r.sort_values(['hold_acc','hold_n'],ascending=[False,False]).assign(val_acc=lambda x:(100*x.val_acc).round(2),hold_acc=lambda x:(100*x.hold_acc).round(2),hold_lo=lambda x:(100*x.hold_lo).round(2)).to_string(index=False));print('75_HOLD_N10',len(r[(r.hold_acc>=.75)&(r.hold_n>=10)]) if len(r) else 0)
# Hand pattern: extreme event reaction (range or volume z high), continuation vs reversal. Direction chosen from pre-hold only, then holdout.
print('\n=== EVENT HAND LOCKED ===');hrs=[]
for condname,cond in {'big_range':df.a_rangez>1,'big_vol':df.a_volz>1,'big_both':(df.a_rangez>1)&(df.a_volz>1),'strong_up':df.a_bodyatr>.5,'strong_dn':df.a_bodyatr<-.5,'up_closehigh':(df.a_bodyatr>0)&(df.a_clv>.6),'dn_closelow':(df.a_bodyatr<0)&(df.a_clv<-.6)}.items():
 for target in targets:
  tr=df[(df.ts<T1)&df.event&cond&df[target].notna()];ho=df[(df.ts>=T1)&(df.ts<T2)&df.event&cond&df[target].notna()]
  if len(tr)<15 or len(ho)<5:continue
  up=float(tr[target].mean());d=1 if up>=.5 else 0;tra=max(up,1-up);k=int((ho[target].astype(int)==d).sum());n=len(ho);L,U=wilson(k,n);hrs.append(dict(cond=condname,target=target,train_n=len(tr),train_acc=tra,dir='UP' if d else 'DOWN',hold_n=n,hold_acc=k/n,hold_lo=L))
h=pd.DataFrame(hrs);print(h.sort_values(['hold_acc','hold_n'],ascending=[False,False]).head(100).assign(train_acc=lambda x:(100*x.train_acc).round(2),hold_acc=lambda x:(100*x.hold_acc).round(2),hold_lo=lambda x:(100*x.hold_lo).round(2)).to_string(index=False));print('HAND75_N10',len(h[(h.hold_acc>=.75)&(h.hold_n>=10)]) if len(h) else 0)
