import requests,math
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier,ExtraTreesClassifier
# Yahoo 1m window: keep within ~30d.
END=int(pd.Timestamp('2026-08-17',tz='UTC').timestamp());START=int(pd.Timestamp('2026-07-19',tz='UTC').timestamp())
def load(sym):
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={START}&period2={END}&interval=1m&events=history&includePrePost=true';r=requests.get(u,timeout=90,headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status();z=r.json()['chart']['result'][0];q=z['indicators']['quote'][0]
 return pd.DataFrame({'ts':pd.to_datetime(z['timestamp'],unit='s',utc=True),'open':q['open'],'high':q['high'],'low':q['low'],'close':q['close'],'volume':q.get('volume',[None]*len(z['timestamp']))}).dropna(subset=['open','high','low','close']).sort_values('ts').drop_duplicates('ts')
M=load('M6E=F');A=load('6E=F');print('M1',len(M),M.ts.min(),M.ts.max(),'A1',len(A),A.ts.min(),A.ts.max())
# Restrict weekdays and exact matched timestamps.
M=M[M.ts.dt.weekday<5].set_index('ts');A=A[A.ts.dt.weekday<5].set_index('ts'); common=M.index.intersection(A.index);M=M.loc[common].copy();A=A.loc[common].copy();print('COMMON1M',len(common))
# Build completed 5m bars from 1m. Timestamp at END of five-minute window, so all OHLC is known at prediction time.
def agg5(z,p):
 g=z.resample('5min',label='right',closed='left').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna(subset=['open','high','low','close']);g.columns=[f'{p}_{c}' for c in g.columns];return g
m5=agg5(M,'m');a5=agg5(A,'a');df=m5.join(a5,how='inner').reset_index().rename(columns={'index':'ts'});df=df.sort_values('ts').reset_index(drop=True);print('BARS5',len(df),df.ts.min(),df.ts.max())
# Features from completed 5m bars.
def add(p):
 c=df[f'{p}_close'];o=df[f'{p}_open'];h=df[f'{p}_high'];l=df[f'{p}_low'];rng=h-l;pc=c.shift();tr=pd.concat([rng,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1);atr=tr.rolling(48).mean();df[f'{p}_r1']=np.log(c).diff()
 for n in [2,3,6,12,24,48,96,288]:df[f'{p}_r{n}']=np.log(c).diff(n)
 for n in [6,12,24,48,96]:
  ma=c.rolling(n).mean();sd=c.rolling(n).std();df[f'{p}_z{n}']=(c-ma)/sd;df[f'{p}_gap{n}']=c/ma-1
 df[f'{p}_range']=rng/atr;df[f'{p}_body']=(c-o)/atr;df[f'{p}_clv']=((c-l)-(h-c))/rng.replace(0,np.nan);df[f'{p}_uw']=(h-df[[f'{p}_open',f'{p}_close']].max(axis=1))/atr;df[f'{p}_lw']=(df[[f'{p}_open',f'{p}_close']].min(axis=1)-l)/atr
 v=np.log1p(pd.to_numeric(df[f'{p}_volume'],errors='coerce').fillna(0).clip(lower=0));df[f'{p}_lv']=v;df[f'{p}_vz48']=(v-v.rolling(48).mean())/v.rolling(48).std();df[f'{p}_vchg']=v-v.shift()
add('a');add('m');df['basis']=df.a_close-df.m_close;df['basis_chg']=df.basis.diff();df['ret_diff']=df.a_r1-df.m_r1;df['vol_rel']=df.a_vz48-df.m_vz48;df['hour']=df.ts.dt.hour;df['minute']=df.ts.dt.minute;df['dow']=df.ts.dt.weekday;mins=df.hour*60+df.minute;df['sin_time']=np.sin(2*np.pi*mins/1440);df['cos_time']=np.cos(2*np.pi*mins/1440);df['london']=(df.hour.between(7,11)).astype(float);df['ny']=(df.hour.between(12,16)).astype(float);df['overlap']=(df.hour.between(12,15)).astype(float)
FEATURES=[c for c in df.columns if c.startswith(('a_r','a_z','a_gap','a_range','a_body','a_clv','a_uw','a_lw','a_lv','a_vz','a_vchg','m_r','m_z','m_gap','m_range','m_body','m_clv','m_uw','m_lw','m_lv','m_vz','m_vchg'))]+['basis','basis_chg','ret_diff','vol_rel','sin_time','cos_time','london','ny','overlap','dow'];df[FEATURES]=df[FEATURES].replace([np.inf,-np.inf],np.nan)
# Map each 5m prediction timestamp to subsequent 1m M6E path. Entry = final 1m close before timestamp / equals 5m close.
Mreset=M.reset_index().sort_values('ts');mts=Mreset.ts.to_numpy();MH=Mreset.high.to_numpy();ML=Mreset.low.to_numpy();MC=Mreset.close.to_numpy();
def outcome(entry_ts,entry,ticks,minutes,pred):
 # pred 1 long, 0 short. Start with 1m bar AT entry_ts, because agg window [t-5,t) ends at t; next minute starts t.
 i=np.searchsorted(mts,np.datetime64(entry_ts),'left');up=entry+ticks*.0001;dn=entry-ticks*.0001;end=np.datetime64(entry_ts+pd.Timedelta(minutes=minutes))
 last=entry
 while i<len(mts) and mts[i]<end:
  hu=MH[i]>=up;ld=ML[i]<=dn;last=MC[i]
  if hu and ld:return -1,'ambiguous',last # conservative loss
  if hu:return (1 if pred==1 else -1),'up',last
  if ld:return (1 if pred==0 else -1),'down',last
  i+=1
 # Neither barrier: conservative classify by time-exit direction; ties loss.
 pnl=(last-entry)*(1 if pred==1 else -1);return (1 if pnl>0 else -1),'timeout',last
# Binary training label based on 1m-resolved first barrier; ambiguous/nohit excluded ONLY from training. Evaluation counts every signal conservatively.
def train_label(ticks,minutes):
 y=np.full(len(df),np.nan)
 for k,r in df.iterrows():
  i=np.searchsorted(mts,np.datetime64(r.ts),'left');up=r.m_close+ticks*.0001;dn=r.m_close-ticks*.0001;end=np.datetime64(r.ts+pd.Timedelta(minutes=minutes));val=np.nan
  while i<len(mts) and mts[i]<end:
   hu=MH[i]>=up;ld=ML[i]<=dn
   if hu and ld:break
   if hu:val=1;break
   if ld:val=0;break
   i+=1
  y[k]=val
 return y

def models(seed=121):return {'l':Pipeline([('i',SimpleImputer(strategy='median')),('s',StandardScaler()),('x',LogisticRegression(C=.12,max_iter=1200))]),'h':Pipeline([('i',SimpleImputer(strategy='median')),('x',HistGradientBoostingClassifier(max_iter=90,learning_rate=.04,max_leaf_nodes=10,min_samples_leaf=80,l2_regularization=5,random_state=seed))]),'e':Pipeline([('i',SimpleImputer(strategy='median')),('x',ExtraTreesClassifier(n_estimators=250,max_depth=7,min_samples_leaf=40,max_features=.5,class_weight='balanced',n_jobs=-1,random_state=seed))])}
def fp(tr,te,target,seed):
 P=[]
 for x in models(seed).values():x.fit(tr[FEATURES],tr[target].astype(int));P.append(x.predict_proba(te[FEATURES])[:,1])
 P=np.vstack(P);return P.mean(0),P.max(0)-P.min(0)
def wilson(k,n,z=1.959963984540054):
 if n<=0:return np.nan,np.nan
 p=k/n;den=1+z*z/n;ctr=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;return ctr-half,ctr+half
# Train Jul19-Jul31, validation Aug1-Aug7, locked holdout Aug10-Aug14.
V0=pd.Timestamp('2026-08-01',tz='UTC');H0=pd.Timestamp('2026-08-10',tz='UTC');H1=pd.Timestamp('2026-08-15',tz='UTC')
rows=[]
for ticks in [1,2,3,5]:
 for minutes in [15,30,60,120]:
  target=f'y_{ticks}_{minutes}';df[target]=train_label(ticks,minutes);tr=df[(df.ts<(V0-pd.Timedelta(minutes=minutes)))&df[target].notna()];va=df[(df.ts>=V0)&(df.ts<H0)&df[target].notna()];ho_all=df[(df.ts>=H0)&(df.ts<H1)].copy()
  if len(tr)<1500 or len(va)<50 or len(ho_all)<100:continue
  pv,sv=fp(tr,va,target,123);vv=va[['ts',target,'m_close']].copy();vv['p']=pv;vv['s']=sv;choices=[]
  for t in [.525,.55,.575,.60,.625,.65,.675,.70,.725,.75,.775,.80]:
   for ag in [False,True]:
    use=(vv.p>=t)|(vv.p<=1-t)
    if ag:use&=vv.s<=.10
    q=vv[use];n=len(q)
    if n<30:continue
    # validation success is strict on full 1m outcome too, not merely label correctness
    wins=0;types={}
    for _,r in q.iterrows():
     pred=int(r.p>=.5);res,typ,_=outcome(r.ts,r.m_close,ticks,minutes,pred);wins+=res>0;types[typ]=types.get(typ,0)+1
    L,U=wilson(wins,n);choices.append((L,wins/n,n,t,ag,types))
  if not choices:continue
  choices.sort(reverse=True,key=lambda z:(z[0],z[1],z[2]));_,vacc,vn,t,ag,vtypes=choices[0]
  # refit before holdout; get probabilities for ALL holdout bars, then signals from fixed threshold
  tr2=df[(df.ts<(H0-pd.Timedelta(minutes=minutes)))&df[target].notna()];ph,sh=fp(tr2,ho_all,target,127);hh=ho_all[['ts','m_close']].copy();hh['p']=ph;hh['s']=sh;use=(hh.p>=t)|(hh.p<=1-t)
  if ag:use&=hh.s<=.10
  q=hh[use].copy();n=len(q);wins=0;types={};pnl_ticks=[]
  # enforce non-overlapping signals: once signal fires, skip until horizon expires
  keep=[];last=None
  for idx,r in q.iterrows():
   if last is None or r.ts>=last+pd.Timedelta(minutes=minutes):keep.append(idx);last=r.ts
  qs=q.loc[keep];sw=0;stypes={};spnl=[]
  for _,r in q.iterrows():
   pred=int(r.p>=.5);res,typ,lastpx=outcome(r.ts,r.m_close,ticks,minutes,pred);wins+=res>0;types[typ]=types.get(typ,0)+1;pnl_ticks.append((lastpx-r.m_close)*(1 if pred else -1)/.0001 if typ=='timeout' else (ticks if res>0 else -ticks))
  for _,r in qs.iterrows():
   pred=int(r.p>=.5);res,typ,lastpx=outcome(r.ts,r.m_close,ticks,minutes,pred);sw+=res>0;stypes[typ]=stypes.get(typ,0)+1;spnl.append((lastpx-r.m_close)*(1 if pred else -1)/.0001 if typ=='timeout' else (ticks if res>0 else -ticks))
  if n:
   L,U=wilson(wins,n);LS,US=wilson(sw,len(qs)) if len(qs) else (np.nan,np.nan);rows.append(dict(ticks=ticks,minutes=minutes,val_n=vn,val_acc=vacc,t=t,agree=ag,hold_n=n,hold_acc=wins/n,hold_lo=L,hold_types=str(types),mean_gross_ticks=float(np.mean(pnl_ticks)),spaced_n=len(qs),spaced_acc=sw/len(qs) if len(qs) else np.nan,spaced_lo=LS,spaced_types=str(stypes),spaced_mean_ticks=float(np.mean(spnl)) if len(spnl) else np.nan))
R=pd.DataFrame(rows);print('=== 1M RESOLVED LOCKED BARRIER RESULTS ===');print(R.sort_values(['spaced_acc','spaced_n'],ascending=[False,False]).assign(val_acc=lambda x:(100*x.val_acc).round(2),hold_acc=lambda x:(100*x.hold_acc).round(2),hold_lo=lambda x:(100*x.hold_lo).round(2),spaced_acc=lambda x:(100*x.spaced_acc).round(2),spaced_lo=lambda x:(100*x.spaced_lo).round(2),mean_gross_ticks=lambda x:x.mean_gross_ticks.round(3),spaced_mean_ticks=lambda x:x.spaced_mean_ticks.round(3)).to_string(index=False));print('STRICT75_ALL_N30',len(R[(R.hold_acc>=.75)&(R.hold_n>=30)]),'STRICT75_SPACED_N30',len(R[(R.spaced_acc>=.75)&(R.spaced_n>=30)]));
if len(R[(R.spaced_acc>=.75)&(R.spaced_n>=30)]):print('CANDIDATES\n',R[(R.spaced_acc>=.75)&(R.spaced_n>=30)].to_string(index=False))
