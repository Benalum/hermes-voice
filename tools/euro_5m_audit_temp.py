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
 return pd.DataFrame({'ts':pd.to_datetime(z['timestamp'],unit='s',utc=True),'open':q['open'],'high':q['high'],'low':q['low'],'close':q['close'],'volume':q.get('volume',[None]*len(z['timestamp']))}).dropna(subset=['open','high','low','close']).sort_values('ts').drop_duplicates('ts').reset_index(drop=True)
s=load('EURUSD=X').rename(columns={c:f's_{c}' for c in ['open','high','low','close','volume']});f=load('6E=F').rename(columns={c:f'f_{c}' for c in ['open','high','low','close','volume']});df=s.merge(f,on='ts',how='inner');df=df[df.ts.dt.weekday<5].sort_values('ts').reset_index(drop=True);print('MATCHED',len(df),df.ts.min(),df.ts.max())
df['sr']=np.log(df.s_close).diff();df['fr']=np.log(df.f_close).diff()
print('ZERO_SPOT_RET_PCT',100*(df.sr==0).mean(),'ZERO_FUT_RET_PCT',100*(df.fr==0).mean())
for lag in range(-4,5):
 # corr current futures return with spot return shifted: positive lag means FUT current vs SPOT future lag bars
 corr=df.fr.corr(df.sr.shift(-lag))
 same=((np.sign(df.fr)==np.sign(df.sr.shift(-lag))) & (df.fr!=0)&(df.sr.shift(-lag)!=0)).sum(); denom=((df.fr!=0)&(df.sr.shift(-lag)!=0)).sum()
 print('FUT_CURRENT_vs_SPOT_LAG',lag,'corr',corr,'signagree_nonzero',same/denom if denom else np.nan,'n',denom)
# Also 6E self autocorrelation/sign transition.
for lag in [1,2,3,6,12]:print('FUT_AUTOCORR',lag,df.fr.corr(df.fr.shift(-lag)))

# Build futures-only target/features. Predict at completion of current 5m futures bar, no spot or concurrent external features.
pc=df.f_close.shift();rng=df.f_high-df.f_low;tr=pd.concat([rng,(df.f_high-pc).abs(),(df.f_low-pc).abs()],axis=1).max(axis=1);atr=tr.rolling(48).mean();df['ret1']=df.fr
for n in [2,3,6,12,24,48,96,288]:df[f'ret{n}']=np.log(df.f_close).diff(n)
for n in [6,12,24,48,96,288]:
 ma=df.f_close.rolling(n).mean();sd=df.f_close.rolling(n).std();df[f'z{n}']=(df.f_close-ma)/sd;df[f'magap{n}']=df.f_close/ma-1
df['range_atr']=rng/atr;df['body_atr']=(df.f_close-df.f_open)/atr;df['clv']=((df.f_close-df.f_low)-(df.f_high-df.f_close))/rng.replace(0,np.nan);df['upperwick']=(df.f_high-df[['f_open','f_close']].max(axis=1))/atr;df['lowerwick']=(df[['f_open','f_close']].min(axis=1)-df.f_low)/atr;df['inside']=((df.f_high<df.f_high.shift())&(df.f_low>df.f_low.shift())).astype(float);df['outside']=((df.f_high>df.f_high.shift())&(df.f_low<df.f_low.shift())).astype(float)
for n in [12,24,48,96]:
 hh=df.f_high.rolling(n).max().shift();ll=df.f_low.rolling(n).min().shift();df[f'donch{n}']=(df.f_close-ll)/(hh-ll);df[f'breakhi{n}']=(df.f_close>hh).astype(float);df[f'breaklo{n}']=(df.f_close<ll).astype(float)
df['rv6']=df.ret1.rolling(6).std();df['rv24']=df.ret1.rolling(24).std();df['rv96']=df.ret1.rolling(96).std();df['volratio']=df.rv6/df.rv96
ch=df.f_close.diff();up=ch.clip(lower=0);dn=(-ch.clip(upper=0))
for n in [3,6,14,28]:
 rs=up.rolling(n).mean()/dn.rolling(n).mean().replace(0,np.nan);df[f'rsi{n}']=100-100/(1+rs)
fv=pd.to_numeric(df.f_volume,errors='coerce').fillna(0).clip(lower=0);lv=np.log1p(fv);df['logvol']=lv;df['volz48']=(lv-lv.rolling(48).mean())/lv.rolling(48).std();df['volz288']=(lv-lv.rolling(288).mean())/lv.rolling(288).std();df['volchg']=lv-lv.shift();df['volxret']=df.volz48*df.ret1
df['hour']=df.ts.dt.hour;df['minute']=df.ts.dt.minute;df['dow']=df.ts.dt.weekday;mins=df.hour*60+df.minute;df['sin_time']=np.sin(2*np.pi*mins/1440);df['cos_time']=np.cos(2*np.pi*mins/1440);df['london']=(df.hour.between(7,11)).astype(float);df['ny']=(df.hour.between(12,16)).astype(float);df['overlap']=(df.hour.between(12,15)).astype(float);df['asia']=(df.hour<=5).astype(float)
for h in [1,3,6,12]:df[f'fwd{h}']=np.log(df.f_close.shift(-h)/df.f_close);df[f'y{h}']=(df[f'fwd{h}']>0).astype(float);df.loc[df[f'fwd{h}'].isna(),f'y{h}']=np.nan
FEATURES=['ret1','ret2','ret3','ret6','ret12','ret24','ret48','ret96','ret288','z6','z12','z24','z48','z96','z288','magap6','magap12','magap24','magap48','magap96','magap288','range_atr','body_atr','clv','upperwick','lowerwick','inside','outside','donch12','donch24','donch48','donch96','breakhi12','breakhi24','breakhi48','breakhi96','breaklo12','breaklo24','breaklo48','breaklo96','rv6','rv24','rv96','volratio','rsi3','rsi6','rsi14','rsi28','logvol','volz48','volz288','volchg','volxret','sin_time','cos_time','london','ny','overlap','asia','dow']
df[FEATURES]=df[FEATURES].replace([np.inf,-np.inf],np.nan)
def models():return {'logit':Pipeline([('i',SimpleImputer(strategy='median')),('s',StandardScaler()),('m',LogisticRegression(C=.12,max_iter=1200))]),'hgb':Pipeline([('i',SimpleImputer(strategy='median')),('m',HistGradientBoostingClassifier(max_iter=90,learning_rate=.04,max_leaf_nodes=10,min_samples_leaf=100,l2_regularization=5,random_state=53))]),'extra':Pipeline([('i',SimpleImputer(strategy='median')),('m',ExtraTreesClassifier(n_estimators=250,max_depth=7,min_samples_leaf=50,max_features=.5,class_weight='balanced',n_jobs=-1,random_state=53))])}
def wilson(k,n,z=1.959963984540054):
 if n<=0:return np.nan,np.nan
 p=k/n;den=1+z*z/n;ctr=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;return ctr-half,ctr+half
# Tests begin after ~4 weeks; weekly walk forward. Target futures itself.
start_test=pd.Timestamp('2026-07-27',tz='UTC');end_test=df.ts.max().floor('D')+pd.Timedelta(days=1);weeks=pd.date_range(start_test,end_test,freq='7D');rows=[]
for h in [1,3,6,12]:
 pieces=[];target=f'y{h}'
 for a in weeks:
  b=min(a+pd.Timedelta(days=7),end_test);trn=df[(df.ts<(a-pd.Timedelta(minutes=5*h)))&df[target].notna()];tst=df[(df.ts>=a)&(df.ts<b)&df[target].notna()]
  if len(trn)<5000 or len(tst)<100:continue
  P=[]
  for m in models().values():m.fit(trn[FEATURES],trn[target].astype(int));P.append(m.predict_proba(tst[FEATURES])[:,1])
  P=np.vstack(P);pieces.append(pd.DataFrame({'ts':tst.ts.values,'y':tst[target].astype(int).values,'p':P.mean(0),'spread':P.max(0)-P.min(0),'fwd':tst[f'fwd{h}'].values}))
 if not pieces:continue
 pr=pd.concat(pieces,ignore_index=True).sort_values('ts').reset_index(drop=True)
 for t in [.525,.55,.575,.60,.625,.65,.675,.70,.725,.75,.775,.80]:
  for ag in [False,True]:
   use=(pr.p>=t)|(pr.p<=1-t)
   if ag:use&=pr.spread<=.10
   q=pr[use].copy();n=len(q)
   if not n:continue
   pred=(q.p>=.5).astype(int);k=int((pred==q.y).sum());L,U=wilson(k,n)
   # require non-overlap by forecast horizon
   keep=[];last=None
   for i,r in q.iterrows():
    tt=pd.Timestamp(r.ts)
    if last is None or tt-last>=pd.Timedelta(minutes=5*h):keep.append(i);last=tt
   qs=q.loc[keep];ps=(qs.p>=.5).astype(int);ks=int((ps==qs.y).sum()) if len(qs) else 0;LS,US=wilson(ks,len(qs)) if len(qs) else (np.nan,np.nan)
   signed=np.where(pred==1,1,-1)*q.fwd;ss=np.where(ps==1,1,-1)*qs.fwd if len(qs) else np.array([])
   rows.append(dict(h=h,t=t,agree=ag,n=n,accuracy=k/n,wilson_lo=L,spaced_n=len(qs),spaced_acc=ks/len(qs) if len(qs) else np.nan,spaced_lo=LS,mean_signed=float(np.mean(signed)),median_signed=float(np.median(signed)),spaced_mean=float(np.mean(ss)) if len(ss) else np.nan,coverage=n/len(pr)))
r=pd.DataFrame(rows);print('=== FUTURES TARGET 5M ===');print(r.sort_values(['spaced_acc','spaced_n'],ascending=[False,False]).head(140).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),spaced_acc=lambda x:(100*x.spaced_acc).round(2),spaced_lo=lambda x:(100*x.spaced_lo).round(2),mean_signed=lambda x:(1e4*x.mean_signed).round(3),median_signed=lambda x:(1e4*x.median_signed).round(3),spaced_mean=lambda x:(1e4*x.spaced_mean).round(3),coverage=lambda x:(100*x.coverage).round(2)).to_string(index=False));print('75_RAW_N30',len(r[(r.accuracy>=.75)&(r.n>=30)]),'75_SPACED_N30',len(r[(r.spaced_acc>=.75)&(r.spaced_n>=30)]))
