import requests, math
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
 return pd.DataFrame({'ts':pd.to_datetime(z['timestamp'],unit='s',utc=True),'open':q['open'],'high':q['high'],'low':q['low'],'close':q['close'],'volume':q.get('volume',[None]*len(z['timestamp']))}).dropna(subset=['open','high','low','close']).sort_values('ts').drop_duplicates('ts').reset_index(drop=True)
spot=load('EURUSD=X');print('SPOT',len(spot),spot.ts.min(),spot.ts.max())
fut=None;fsym=None
for s in ['6E=F','M6E=F','EUR=F']:
 try:
  z=load(s);print('FUTPROBE',s,len(z),z.ts.min(),z.ts.max(),'vol+',int(pd.to_numeric(z.volume,errors='coerce').fillna(0).gt(0).sum()))
  if fut is None and len(z)>3000:fut=z;fsym=s
 except Exception as e:print('FUTFAIL',s,repr(e))
# Use spot as primary target; add futures exact-time features if available.
df=spot.rename(columns={c:f's_{c}' for c in ['open','high','low','close','volume']});df=df[df.ts.dt.weekday<5].copy().reset_index(drop=True)
if fut is not None:
 f=fut.rename(columns={c:f'f_{c}' for c in ['open','high','low','close','volume']})
 df=df.merge(f,on='ts',how='left');print('USING_FUT',fsym,'matched',int(df.f_close.notna().sum()))
try:
 dxy=load('DX=F')[['ts','close']].rename(columns={'close':'dxy'});df=df.merge(dxy,on='ts',how='left')
except Exception as e:print('DXYFAIL',repr(e));df['dxy']=np.nan
# Features at END of current completed 5m bar. Yahoo timestamps label bar start, but prediction target starts after OHLC completion.
pc=df.s_close.shift();rng=df.s_high-df.s_low;tr=pd.concat([rng,(df.s_high-pc).abs(),(df.s_low-pc).abs()],axis=1).max(axis=1);atr=tr.rolling(48).mean()
df['ret1']=np.log(df.s_close).diff()
for n in [2,3,6,12,24,48,96,288]:df[f'ret{n}']=np.log(df.s_close).diff(n)
for n in [6,12,24,48,96,288]:
 ma=df.s_close.rolling(n).mean();sd=df.s_close.rolling(n).std();df[f'z{n}']=(df.s_close-ma)/sd;df[f'magap{n}']=df.s_close/ma-1
# Current completed candle geometry.
df['range_atr']=rng/atr;df['body_atr']=(df.s_close-df.s_open)/atr;df['clv']=((df.s_close-df.s_low)-(df.s_high-df.s_close))/rng.replace(0,np.nan);df['upperwick']=(df.s_high-df[['s_open','s_close']].max(axis=1))/atr;df['lowerwick']=(df[['s_open','s_close']].min(axis=1)-df.s_low)/atr;df['inside']=((df.s_high<df.s_high.shift())&(df.s_low>df.s_low.shift())).astype(float);df['outside']=((df.s_high>df.s_high.shift())&(df.s_low<df.s_low.shift())).astype(float)
for n in [12,24,48,96]:
 hh=df.s_high.rolling(n).max().shift();ll=df.s_low.rolling(n).min().shift();df[f'donch{n}']=(df.s_close-ll)/(hh-ll);df[f'breakhi{n}']=(df.s_close>hh).astype(float);df[f'breaklo{n}']=(df.s_close<ll).astype(float)
# Volatility and RSI.
df['vol6']=df.ret1.rolling(6).std();df['vol24']=df.ret1.rolling(24).std();df['vol96']=df.ret1.rolling(96).std();df['volratio']=df.vol6/df.vol96
ch=df.s_close.diff();up=ch.clip(lower=0);dn=(-ch.clip(upper=0))
for n in [3,6,14,28]:
 rs=up.rolling(n).mean()/dn.rolling(n).mean().replace(0,np.nan);df[f'rsi{n}']=100-100/(1+rs)
# Futures features/volume if available.
if fut is not None:
 fv=pd.to_numeric(df.f_volume,errors='coerce').fillna(0).clip(lower=0);lv=np.log1p(fv);df['fret1']=np.log(df.f_close).diff();df['fret3']=np.log(df.f_close).diff(3);df['basis']=df.f_close-df.s_close;df['basis_chg']=df.basis.diff();df['logvol']=lv;df['volz48']=(lv-lv.rolling(48).mean())/lv.rolling(48).std();df['volz288']=(lv-lv.rolling(288).mean())/lv.rolling(288).std();df['volchg']=lv-lv.shift();df['volxret']=df.volz48*df.fret1
# DXY exact bar.
df['dxy_ret1']=np.log(df.dxy).diff();df['dxy_ret3']=np.log(df.dxy).diff(3);df['dxy_ret12']=np.log(df.dxy).diff(12)
# Time/session.
df['hour']=df.ts.dt.hour;df['minute']=df.ts.dt.minute;df['dow']=df.ts.dt.weekday;mins=df.hour*60+df.minute;df['sin_time']=np.sin(2*np.pi*mins/1440);df['cos_time']=np.cos(2*np.pi*mins/1440);df['london']=(df.hour.between(7,11)).astype(float);df['ny']=(df.hour.between(12,16)).astype(float);df['overlap']=(df.hour.between(12,15)).astype(float);df['asia']=(df.hour<=5).astype(float)
# Targets 1,3,6,12 bars = 5,15,30,60 min.
for h in [1,3,6,12]:df[f'fret_target{h}']=np.log(df.s_close.shift(-h)/df.s_close);df[f'y{h}']=(df[f'fret_target{h}']>0).astype(float);df.loc[df[f'fret_target{h}'].isna(),f'y{h}']=np.nan
FEATURES=['ret1','ret2','ret3','ret6','ret12','ret24','ret48','ret96','ret288','z6','z12','z24','z48','z96','z288','magap6','magap12','magap24','magap48','magap96','magap288','range_atr','body_atr','clv','upperwick','lowerwick','inside','outside','donch12','donch24','donch48','donch96','breakhi12','breakhi24','breakhi48','breakhi96','breaklo12','breaklo24','breaklo48','breaklo96','vol6','vol24','vol96','volratio','rsi3','rsi6','rsi14','rsi28','dxy_ret1','dxy_ret3','dxy_ret12','sin_time','cos_time','london','ny','overlap','asia','dow']
for c in ['fret1','fret3','basis','basis_chg','logvol','volz48','volz288','volchg','volxret']:
 if c in df:FEATURES.append(c)
df[FEATURES]=df[FEATURES].replace([np.inf,-np.inf],np.nan);print('ROWS',len(df),'FEATURES',len(FEATURES))

def models():return {'logit':Pipeline([('i',SimpleImputer(strategy='median')),('s',StandardScaler()),('m',LogisticRegression(C=.12,max_iter=1200))]),'hgb':Pipeline([('i',SimpleImputer(strategy='median')),('m',HistGradientBoostingClassifier(max_iter=90,learning_rate=.04,max_leaf_nodes=10,min_samples_leaf=100,l2_regularization=5,random_state=31))]),'extra':Pipeline([('i',SimpleImputer(strategy='median')),('m',ExtraTreesClassifier(n_estimators=250,max_depth=7,min_samples_leaf=50,max_features=.5,class_weight='balanced',n_jobs=-1,random_state=31))])}
def wilson(k,n,z=1.959963984540054):
 if n<=0:return np.nan,np.nan
 p=k/n;den=1+z*z/n;ctr=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;return ctr-half,ctr+half
# Weekly expanding walk-forward. Start tests after ~4 weeks.
start_test=pd.Timestamp('2026-07-27',tz='UTC');end_test=df.ts.max().floor('D')+pd.Timedelta(days=1);weeks=pd.date_range(start_test,end_test,freq='7D')
rows=[]
for h in [1,3,6,12]:
 pieces=[];target=f'y{h}'
 for a in weeks:
  b=min(a+pd.Timedelta(days=7),end_test);trn=df[(df.ts<(a-pd.Timedelta(minutes=5*h)))&df[target].notna()];tst=df[(df.ts>=a)&(df.ts<b)&df[target].notna()]
  if len(trn)<5000 or len(tst)<100:continue
  P=[]
  for m in models().values():m.fit(trn[FEATURES],trn[target].astype(int));P.append(m.predict_proba(tst[FEATURES])[:,1])
  P=np.vstack(P);pieces.append(pd.DataFrame({'ts':tst.ts.values,'y':tst[target].astype(int).values,'p':P.mean(0),'spread':P.max(0)-P.min(0)}))
 if not pieces:continue
 pr=pd.concat(pieces,ignore_index=True).sort_values('ts').reset_index(drop=True)
 for t in [.525,.55,.575,.60,.625,.65,.675,.70,.725,.75,.775,.80]:
  for ag in [False,True]:
   use=(pr.p>=t)|(pr.p<=1-t)
   if ag:use&=pr.spread<=.10
   q=pr[use].copy();n=len(q)
   if n:
    k=int((((q.p>=.5).astype(int))==q.y).sum());L,U=wilson(k,n)
    # Non-overlap by horizon bars for an effective-sample check.
    keep=[];last=None
    for i,r in q.iterrows():
     tt=pd.Timestamp(r.ts)
     if last is None or tt-last>=pd.Timedelta(minutes=5*h):keep.append(i);last=tt
    qs=q.loc[keep];ks=int((((qs.p>=.5).astype(int))==qs.y).sum()) if len(qs) else 0;LS,US=wilson(ks,len(qs)) if len(qs) else (np.nan,np.nan)
    rows.append(dict(h=h,t=t,agree=ag,n=n,accuracy=k/n,wilson_lo=L,spaced_n=len(qs),spaced_acc=ks/len(qs) if len(qs) else np.nan,spaced_lo=LS,coverage=n/len(pr)))
r=pd.DataFrame(rows);print('=== 5M SELECTIVE ===');print(r.sort_values(['spaced_acc','spaced_n'],ascending=[False,False]).head(140).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),spaced_acc=lambda x:(100*x.spaced_acc).round(2),spaced_lo=lambda x:(100*x.spaced_lo).round(2),coverage=lambda x:(100*x.coverage).round(2)).to_string(index=False));print('75_RAW_N30',len(r[(r.accuracy>=.75)&(r.n>=30)]),'75_SPACED_N30',len(r[(r.spaced_acc>=.75)&(r.spaced_n>=30)]))
