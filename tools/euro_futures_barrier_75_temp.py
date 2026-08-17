import requests,math
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier,ExtraTreesClassifier
START=int(pd.Timestamp('2024-09-15',tz='UTC').timestamp());END=int(pd.Timestamp('2026-08-17',tz='UTC').timestamp())
def load(sym):
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={START}&period2={END}&interval=1h&events=history&includePrePost=true'
 r=requests.get(u,timeout=90,headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status();z=r.json()['chart']['result'][0];q=z['indicators']['quote'][0]
 return pd.DataFrame({'ts':pd.to_datetime(z['timestamp'],unit='s',utc=True),'open':q['open'],'high':q['high'],'low':q['low'],'close':q['close'],'volume':q.get('volume',[None]*len(z['timestamp']))}).dropna(subset=['open','high','low','close']).sort_values('ts').drop_duplicates('ts').reset_index(drop=True)
df=load('6E=F');df=df[df.ts.dt.weekday<5].reset_index(drop=True);print('ROWS',len(df),df.ts.min(),df.ts.max())
# completed-current-bar features
pc=df.close.shift();rng=df.high-df.low;tr=pd.concat([rng,(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1);atr=tr.rolling(24).mean();df['ret1']=np.log(df.close).diff()
for n in [2,3,6,12,24,48,120]:df[f'ret{n}']=np.log(df.close).diff(n)
for n in [6,12,24,48,120]:
 ma=df.close.rolling(n).mean();sd=df.close.rolling(n).std();df[f'z{n}']=(df.close-ma)/sd;df[f'magap{n}']=df.close/ma-1
df['range_atr']=rng/atr;df['body_atr']=(df.close-df.open)/atr;df['clv']=((df.close-df.low)-(df.high-df.close))/rng.replace(0,np.nan);df['upperwick']=(df.high-df[['open','close']].max(axis=1))/atr;df['lowerwick']=(df[['open','close']].min(axis=1)-df.low)/atr
for n in [6,12,24,48]:
 hh=df.high.rolling(n).max().shift();ll=df.low.rolling(n).min().shift();df[f'donch{n}']=(df.close-ll)/(hh-ll);df[f'breakhi{n}']=(df.close>hh).astype(float);df[f'breaklo{n}']=(df.close<ll).astype(float)
v=pd.to_numeric(df.volume,errors='coerce').fillna(0).clip(lower=0);lv=np.log1p(v);df['logvol']=lv;df['volz24']=(lv-lv.rolling(24).mean())/lv.rolling(24).std();df['volz120']=(lv-lv.rolling(120).mean())/lv.rolling(120).std();df['volchg']=lv-lv.shift();df['volxret']=df.volz24*df.ret1
df['rv6']=df.ret1.rolling(6).std();df['rv24']=df.ret1.rolling(24).std();df['volratio']=df.rv6/df.rv24
ch=df.close.diff();up=ch.clip(lower=0);dn=(-ch.clip(upper=0))
for n in [3,6,14]:
 rs=up.rolling(n).mean()/dn.rolling(n).mean().replace(0,np.nan);df[f'rsi{n}']=100-100/(1+rs)
df['hour']=df.ts.dt.hour;df['dow']=df.ts.dt.weekday;df['sin_hour']=np.sin(2*np.pi*df.hour/24);df['cos_hour']=np.cos(2*np.pi*df.hour/24);df['london']=(df.hour.between(7,11)).astype(float);df['ny']=(df.hour.between(12,16)).astype(float);df['overlap']=(df.hour.between(12,15)).astype(float)
FEATURES=['ret1','ret2','ret3','ret6','ret12','ret24','ret48','ret120','z6','z12','z24','z48','z120','magap6','magap12','magap24','magap48','magap120','range_atr','body_atr','clv','upperwick','lowerwick','donch6','donch12','donch24','donch48','breakhi6','breakhi12','breakhi24','breakhi48','breaklo6','breaklo12','breaklo24','breaklo48','logvol','volz24','volz120','volchg','volxret','rv6','rv24','volratio','rsi3','rsi6','rsi14','sin_hour','cos_hour','london','ny','overlap','dow']
df[FEATURES]=df[FEATURES].replace([np.inf,-np.inf],np.nan)
# First-hit labels. 6E minimum tick is 0.00005; use 10/20/30/40 ticks = .0005/.001/.0015/.002.
def make_label(dist,horizon):
 y=np.full(len(df),np.nan);timehit=np.full(len(df),np.nan)
 C=df.close.to_numpy();H=df.high.to_numpy();L=df.low.to_numpy()
 for i in range(len(df)-1):
  up=C[i]+dist;dn=C[i]-dist
  for j in range(i+1,min(len(df),i+1+horizon)):
   hu=H[j]>=up;ld=L[j]<=dn
   if hu and ld:break # ambiguous same hourly bar: discard
   if hu:y[i]=1;timehit[i]=j-i;break
   if ld:y[i]=0;timehit[i]=j-i;break
 return y,timehit

def models():return {'logit':Pipeline([('i',SimpleImputer(strategy='median')),('s',StandardScaler()),('m',LogisticRegression(C=.12,max_iter=1500))]),'hgb':Pipeline([('i',SimpleImputer(strategy='median')),('m',HistGradientBoostingClassifier(max_iter=100,learning_rate=.04,max_leaf_nodes=10,min_samples_leaf=60,l2_regularization=5,random_state=41))]),'extra':Pipeline([('i',SimpleImputer(strategy='median')),('m',ExtraTreesClassifier(n_estimators=300,max_depth=7,min_samples_leaf=35,max_features=.5,class_weight='balanced',n_jobs=-1,random_state=41))])}
def wilson(k,n,z=1.959963984540054):
 if n<=0:return np.nan,np.nan
 p=k/n;den=1+z*z/n;ctr=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;return ctr-half,ctr+half
quarters=pd.period_range('2025Q2','2026Q3',freq='Q');rows=[]
for ticks in [10,20,30,40]:
 dist=ticks*.00005
 for horizon in [6,12,24]:
  y,th=make_label(dist,horizon);target=f'y_b_{ticks}_{horizon}';df[target]=y
  pieces=[]
  for per in quarters:
   a=per.start_time.tz_localize('UTC');b=(per+1).start_time.tz_localize('UTC');trn=df[(df.ts<(a-pd.Timedelta(hours=horizon)))&df[target].notna()];tst=df[(df.ts>=a)&(df.ts<b)&df[target].notna()]
   if len(trn)<2000 or len(tst)<50:continue
   P=[]
   for m in models().values():m.fit(trn[FEATURES],trn[target].astype(int));P.append(m.predict_proba(tst[FEATURES])[:,1])
   P=np.vstack(P);pieces.append(pd.DataFrame({'ts':tst.ts.values,'y':tst[target].astype(int).values,'p':P.mean(0),'spread':P.max(0)-P.min(0)}))
  if not pieces:continue
  pr=pd.concat(pieces,ignore_index=True).sort_values('ts').reset_index(drop=True)
  for t in [.525,.55,.575,.60,.625,.65,.675,.70,.725,.75,.775,.80]:
   for ag in [False,True]:
    use=(pr.p>=t)|(pr.p<=1-t)
    if ag:use&=pr.spread<=.10
    q=pr[use];n=len(q)
    if not n:continue
    k=int((((q.p>=.5).astype(int))==q.y).sum());L,U=wilson(k,n)
    # spacing by horizon hours reduces duplicate episodes
    keep=[];last=None
    for idx,r in q.iterrows():
     tt=pd.Timestamp(r.ts)
     if last is None or tt-last>=pd.Timedelta(hours=horizon):keep.append(idx);last=tt
    qs=q.loc[keep];ks=int((((qs.p>=.5).astype(int))==qs.y).sum()) if len(qs) else 0;LS,US=wilson(ks,len(qs)) if len(qs) else (np.nan,np.nan)
    recent=q[pd.to_datetime(q.ts)>=pd.Timestamp('2026-01-01')];kr=int((((recent.p>=.5).astype(int))==recent.y).sum()) if len(recent) else 0;LR,UR=wilson(kr,len(recent)) if len(recent) else (np.nan,np.nan)
    rows.append(dict(ticks=ticks,horizon=horizon,t=t,agree=ag,n=n,accuracy=k/n,wilson_lo=L,spaced_n=len(qs),spaced_acc=ks/len(qs) if len(qs) else np.nan,spaced_lo=LS,recent_n=len(recent),recent_acc=kr/len(recent) if len(recent) else np.nan,coverage=n/len(pr)))
r=pd.DataFrame(rows);print('=== BARRIER RESULTS ===');print(r.sort_values(['spaced_acc','spaced_n'],ascending=[False,False]).head(180).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),spaced_acc=lambda x:(100*x.spaced_acc).round(2),spaced_lo=lambda x:(100*x.spaced_lo).round(2),recent_acc=lambda x:(100*x.recent_acc).round(2),coverage=lambda x:(100*x.coverage).round(2)).to_string(index=False));print('75_RAW_N30',len(r[(r.accuracy>=.75)&(r.n>=30)]),'75_SPACED_N30',len(r[(r.spaced_acc>=.75)&(r.spaced_n>=30)]));
if len(r[(r.spaced_acc>=.75)&(r.spaced_n>=30)]):print('CANDIDATES\n',r[(r.spaced_acc>=.75)&(r.spaced_n>=30)].sort_values('spaced_lo',ascending=False).to_string(index=False))
