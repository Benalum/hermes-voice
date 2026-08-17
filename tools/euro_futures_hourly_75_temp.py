import requests, math
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
 return pd.DataFrame({'ts':pd.to_datetime(z['timestamp'],unit='s',utc=True),'open':q['open'],'high':q['high'],'low':q['low'],'close':q['close'],'volume':q.get('volume',[None]*len(z['timestamp']))}).dropna(subset=['open','high','low','close']).sort_values('ts').drop_duplicates('ts')
FUT=None;FSYM=None
for s in ['6E=F','M6E=F','EUR=F']:
 try:
  z=load(s);print('PROBE',s,len(z),z.ts.min(),z.ts.max(),'volume_nonzero',int(pd.to_numeric(z.volume,errors='coerce').fillna(0).gt(0).sum()))
  if FUT is None and len(z)>3000:FUT=z;FSYM=s
 except Exception as e:print('FAIL',s,repr(e))
if FUT is None:raise RuntimeError('no Euro futures symbol')
spot=load('EURUSD=X')[['ts','close']].rename(columns={'close':'spot'})
try:dxy=load('DX=F')[['ts','close']].rename(columns={'close':'dxy'})
except Exception as e:dxy=pd.DataFrame(columns=['ts','dxy']);print('DXYFAIL',repr(e))
df=FUT.rename(columns={'open':'fopen','high':'fhigh','low':'flow','close':'fclose','volume':'fvol'}).merge(spot,on='ts',how='left').merge(dxy,on='ts',how='left').sort_values('ts').reset_index(drop=True)
df=df[df.ts.dt.weekday<5].copy().reset_index(drop=True);df[['spot','dxy']]=df[['spot','dxy']].ffill(limit=3)
print('USING',FSYM,'ROWS',len(df))
# Features known at completion of current hourly bar.
pc=df.fclose.shift();rng=df.fhigh-df.flow;tr=pd.concat([rng,(df.fhigh-pc).abs(),(df.flow-pc).abs()],axis=1).max(axis=1);atr=tr.rolling(24).mean()
df['ret1']=np.log(df.fclose).diff()
for n in [2,3,6,12,24,48,120]:df[f'ret{n}']=np.log(df.fclose).diff(n)
for n in [6,12,24,48,120]:
 ma=df.fclose.rolling(n).mean();sd=df.fclose.rolling(n).std();df[f'z{n}']=(df.fclose-ma)/sd;df[f'magap{n}']=df.fclose/ma-1
df['range_atr']=rng/atr;df['body_atr']=(df.fclose-df.fopen)/atr;df['clv']=((df.fclose-df.flow)-(df.fhigh-df.fclose))/rng.replace(0,np.nan);df['upperwick']=(df.fhigh-df[['fopen','fclose']].max(axis=1))/atr;df['lowerwick']=(df[['fopen','fclose']].min(axis=1)-df.flow)/atr
for n in [6,12,24,48]:
 hh=df.fhigh.rolling(n).max().shift();ll=df.flow.rolling(n).min().shift();df[f'donch{n}']=(df.fclose-ll)/(hh-ll);df[f'breakhi{n}']=(df.fclose>hh).astype(float);df[f'breaklo{n}']=(df.fclose<ll).astype(float)
# Volume (Yahoo futures hourly). Work with log1p; handle roll/session zeros.
v=pd.to_numeric(df.fvol,errors='coerce').fillna(0).clip(lower=0);lv=np.log1p(v);df['logvol']=lv;df['vol_z24']=(lv-lv.rolling(24).mean())/lv.rolling(24).std();df['vol_z120']=(lv-lv.rolling(120).mean())/lv.rolling(120).std();df['vol_chg']=lv-lv.shift(1);df['vol_price_up']=df.vol_z24*df.ret1;df['vol_absret']=df.vol_z24*df.ret1.abs()
# Spot/futures basis and cross asset.
df['basis']=df.fclose-df.spot;df['basis_chg1']=df.basis.diff();df['basis_chg6']=df.basis.diff(6);df['spot_ret1']=np.log(df.spot).diff();df['spot_ret6']=np.log(df.spot).diff(6);df['fut_vs_spot']=df.ret1-df.spot_ret1
if df.dxy.notna().sum()>1000:
 for n in [1,3,6,12]:df[f'dxy_ret{n}']=np.log(df.dxy).diff(n)
# Volatility/session.
df['vol6']=df.ret1.rolling(6).std();df['vol24']=df.ret1.rolling(24).std();df['volratio']=df.vol6/df.vol24;df['hour']=df.ts.dt.hour;df['dow']=df.ts.dt.weekday;df['sin_hour']=np.sin(2*np.pi*df.hour/24);df['cos_hour']=np.cos(2*np.pi*df.hour/24);df['london']=(df.hour.between(7,11)).astype(float);df['ny']=(df.hour.between(12,16)).astype(float);df['overlap']=(df.hour.between(12,15)).astype(float)
for h in [1,2,3,6,12]:df[f'fret{h}']=np.log(df.fclose.shift(-h)/df.fclose);df[f'y{h}']=(df[f'fret{h}']>0).astype(float);df.loc[df[f'fret{h}'].isna(),f'y{h}']=np.nan
FEATURES=[c for c in df.columns if c.startswith(('ret','z','magap','donch','breakhi','breaklo','vol_','dxy_ret'))]+['range_atr','body_atr','clv','upperwick','lowerwick','logvol','vol_z24','vol_z120','vol_chg','basis','basis_chg1','basis_chg6','spot_ret1','spot_ret6','fut_vs_spot','vol6','vol24','volratio','sin_hour','cos_hour','london','ny','overlap','dow']
FEATURES=list(dict.fromkeys([c for c in FEATURES if c in df.columns and not c.startswith('fret')]));df[FEATURES]=df[FEATURES].replace([np.inf,-np.inf],np.nan)
print('FEATURES',len(FEATURES))
def models():return {'logit':Pipeline([('i',SimpleImputer(strategy='median')),('s',StandardScaler()),('m',LogisticRegression(C=.12,max_iter=1500))]),'hgb':Pipeline([('i',SimpleImputer(strategy='median')),('m',HistGradientBoostingClassifier(max_iter=100,learning_rate=.04,max_leaf_nodes=10,min_samples_leaf=60,l2_regularization=5,random_state=23))]),'extra':Pipeline([('i',SimpleImputer(strategy='median')),('m',ExtraTreesClassifier(n_estimators=300,max_depth=7,min_samples_leaf=35,max_features=.5,class_weight='balanced',n_jobs=-1,random_state=23))])}
def wilson(k,n,z=1.959963984540054):
 if n<=0:return np.nan,np.nan
 p=k/n;den=1+z*z/n;ctr=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;return ctr-half,ctr+half
quarters=pd.period_range('2025Q2','2026Q3',freq='Q');rows=[]
for h in [1,2,3,6,12]:
 pieces=[];target=f'y{h}'
 for per in quarters:
  a=per.start_time.tz_localize('UTC');b=(per+1).start_time.tz_localize('UTC');trn=df[(df.ts<(a-pd.Timedelta(hours=h)))&df[target].notna()];tst=df[(df.ts>=a)&(df.ts<b)&df[target].notna()]
  if len(trn)<3000 or len(tst)<100:continue
  P=[]
  for m in models().values():m.fit(trn[FEATURES],trn[target].astype(int));P.append(m.predict_proba(tst[FEATURES])[:,1])
  P=np.vstack(P);pieces.append(pd.DataFrame({'ts':tst.ts.values,'y':tst[target].astype(int).values,'p':P.mean(0),'spread':P.max(0)-P.min(0)}))
 if not pieces:continue
 pr=pd.concat(pieces,ignore_index=True)
 for t in [.525,.55,.575,.60,.625,.65,.675,.70,.725,.75,.775,.80]:
  for ag in [False,True]:
   use=(pr.p>=t)|(pr.p<=1-t)
   if ag:use&=pr.spread<=.10
   q=pr[use];n=len(q)
   if not n:continue
   k=int((((q.p>=.5).astype(int))==q.y).sum());L,U=wilson(k,n);recent=q[pd.to_datetime(q.ts)>=pd.Timestamp('2026-01-01')];kr=int((((recent.p>=.5).astype(int))==recent.y).sum()) if len(recent) else 0;LR,UR=wilson(kr,len(recent)) if len(recent) else (np.nan,np.nan)
   rows.append(dict(h=h,t=t,agree=ag,n=n,accuracy=k/n,wilson_lo=L,coverage=n/len(pr),recent_n=len(recent),recent_acc=kr/len(recent) if len(recent) else np.nan,recent_lo=LR))
r=pd.DataFrame(rows);print('=== FUTURES HOURLY SELECTIVE ===');print(r.sort_values(['accuracy','n'],ascending=[False,False]).head(120).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),coverage=lambda x:(100*x.coverage).round(2),recent_acc=lambda x:(100*x.recent_acc).round(2),recent_lo=lambda x:(100*x.recent_lo).round(2)).to_string(index=False));print('75_N30',len(r[(r.accuracy>=.75)&(r.n>=30)]))
