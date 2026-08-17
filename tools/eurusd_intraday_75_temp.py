import requests, math, time
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier

# Yahoo hourly data, max practical window ~730d. Split chronologically; no random CV.
end=int(pd.Timestamp('2026-08-17',tz='UTC').timestamp()); start=int(pd.Timestamp('2024-08-01',tz='UTC').timestamp())
u=f'https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X?period1={start}&period2={end}&interval=1h&events=history&includePrePost=true'
r=requests.get(u,timeout=90,headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status();j=r.json()['chart']['result'][0]
ts=pd.to_datetime(j['timestamp'],unit='s',utc=True);q=j['indicators']['quote'][0]
df=pd.DataFrame({'ts':ts,'open':q['open'],'high':q['high'],'low':q['low'],'close':q['close']}).dropna().sort_values('ts').drop_duplicates('ts').reset_index(drop=True)
print('HOURLY',len(df),df.ts.min(),df.ts.max())
# Yahoo FX may include flat weekend bars; remove near-zero range and weekend.
df=df[df.ts.dt.weekday<5].copy().reset_index(drop=True)

pc=df.close.shift(); rng=(df.high-df.low); tr=pd.concat([rng,(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1);atr24=tr.rolling(24).mean()
df['ret1']=np.log(df.close).diff();
for n in [2,3,4,6,12,24,48,120]:df[f'ret{n}']=np.log(df.close).diff(n)
for n in [6,12,24,48,120]:
 ma=df.close.rolling(n).mean();sd=df.close.rolling(n).std();df[f'z{n}']=(df.close-ma)/sd;df[f'magap{n}']=df.close/ma-1
# candle geometry
df['range_atr']=rng/atr24;df['body_atr']=(df.close-df.open)/atr24;df['clv']=((df.close-df.low)-(df.high-df.close))/rng.replace(0,np.nan)
df['upperwick']=(df.high-df[['open','close']].max(axis=1))/atr24;df['lowerwick']=(df[['open','close']].min(axis=1)-df.low)/atr24
df['inside']=((df.high<df.high.shift())&(df.low>df.low.shift())).astype(float);df['outside']=((df.high>df.high.shift())&(df.low<df.low.shift())).astype(float)
for n in [6,12,24,48]:
 hh=df.high.rolling(n).max().shift();ll=df.low.rolling(n).min().shift();df[f'donch{n}']=(df.close-ll)/(hh-ll);df[f'breakhi{n}']=(df.close>hh).astype(float);df[f'breaklo{n}']=(df.close<ll).astype(float)
# volatility regime
df['vol6']=df.ret1.rolling(6).std();df['vol24']=df.ret1.rolling(24).std();df['volratio']=df.vol6/df.vol24
# RSI
chg=df.close.diff();up=chg.clip(lower=0);dn=(-chg.clip(upper=0))
for n in [3,6,14]:
 rs=up.rolling(n).mean()/dn.rolling(n).mean().replace(0,np.nan);df[f'rsi{n}']=100-100/(1+rs)
# UTC session/time cyclical features
df['hour']=df.ts.dt.hour;df['dow']=df.ts.dt.weekday
df['sin_hour']=np.sin(2*np.pi*df.hour/24);df['cos_hour']=np.cos(2*np.pi*df.hour/24)
df['london']=(df.hour.between(7,11)).astype(float);df['ny']=(df.hour.between(12,16)).astype(float);df['overlap']=(df.hour.between(12,15)).astype(float);df['asia']=(df.hour<=5).astype(float)
# previous session/day features
df['day']=df.ts.dt.floor('D');daily=df.groupby('day').agg(day_open=('open','first'),day_high=('high','max'),day_low=('low','min'),day_close=('close','last'))
daily['prev_day_ret']=np.log(daily.day_close/daily.day_close.shift());daily['prev_range']=(daily.day_high-daily.day_low)/daily.day_close
df=df.merge(daily[['prev_day_ret','prev_range']],left_on='day',right_index=True,how='left')

for h in [1,2,3,6,12]:
 df[f'fret{h}']=np.log(df.close.shift(-h)/df.close);df[f'y{h}']=(df[f'fret{h}']>0).astype(float);df.loc[df[f'fret{h}'].isna(),f'y{h}']=np.nan

FEATURES=['ret1','ret2','ret3','ret4','ret6','ret12','ret24','ret48','ret120','z6','z12','z24','z48','z120','magap6','magap12','magap24','magap48','magap120','range_atr','body_atr','clv','upperwick','lowerwick','inside','outside','donch6','donch12','donch24','donch48','breakhi6','breakhi12','breakhi24','breakhi48','breaklo6','breaklo12','breaklo24','breaklo48','vol6','vol24','volratio','rsi3','rsi6','rsi14','sin_hour','cos_hour','london','ny','overlap','asia','dow','prev_day_ret','prev_range']

def models():return {
 'logit':Pipeline([('imp',SimpleImputer(strategy='median')),('sc',StandardScaler()),('m',LogisticRegression(C=.15,max_iter=1500))]),
 'hgb':Pipeline([('imp',SimpleImputer(strategy='median')),('m',HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=10,min_samples_leaf=60,learning_rate=.04,l2_regularization=4,random_state=4))]),
 'extra':Pipeline([('imp',SimpleImputer(strategy='median')),('m',ExtraTreesClassifier(n_estimators=300,max_depth=7,min_samples_leaf=35,max_features=.5,class_weight='balanced',n_jobs=-1,random_state=4))])}

def wilson(k,n,z=1.959963984540054):
 if n<=0:return np.nan,np.nan
 p=k/n;den=1+z*z/n;ctr=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;return ctr-half,ctr+half

# Rolling quarterly walk-forward: minimum first 8 months train, test each subsequent quarter; expanding history.
preds={}
quarters=pd.period_range('2025Q2','2026Q3',freq='Q')
for h in [1,2,3,6,12]:
 pieces=[];target=f'y{h}'
 for per in quarters:
  t0=per.start_time.tz_localize('UTC');t1=(per+1).start_time.tz_localize('UTC')
  trn=df[(df.ts<t0)&df[target].notna()];tst=df[(df.ts>=t0)&(df.ts<t1)&df[target].notna()]
  if len(trn)<3500 or len(tst)<100:continue
  ps=[]
  for m in models().values():m.fit(trn[FEATURES],trn[target].astype(int));ps.append(m.predict_proba(tst[FEATURES])[:,1])
  P=np.vstack(ps);p=P.mean(axis=0);spread=P.max(axis=0)-P.min(axis=0)
  pieces.append(pd.DataFrame({'ts':tst.ts.values,'y':tst[target].astype(int).values,'p':p,'spread':spread,'p0':P[0],'p1':P[1],'p2':P[2]}))
 preds[h]=pd.concat(pieces,ignore_index=True).sort_values('ts') if pieces else pd.DataFrame()

print('=== HOURLY SELECTIVE WALK FORWARD ===')
rows=[]
for h,pr in preds.items():
 if len(pr)==0:continue
 for t in [.525,.55,.575,.60,.625,.65,.675,.70,.725,.75,.775,.80]:
  for agree in [False,True]:
   use=(pr.p>=t)|(pr.p<=1-t)
   if agree: use &= pr.spread<=.10
   q=pr[use];n=len(q)
   if not n:continue
   k=int((((q.p>=.5).astype(int))==q.y).sum());L,U=wilson(k,n)
   recent=q[pd.to_datetime(q.ts)>=pd.Timestamp('2026-01-01')];kr=int((((recent.p>=.5).astype(int))==recent.y).sum()) if len(recent) else 0;LR,UR=wilson(kr,len(recent)) if len(recent) else (np.nan,np.nan)
   rows.append(dict(h=h,t=t,agree=agree,n=n,accuracy=k/n,wilson_lo=L,coverage=n/len(pr),recent_n=len(recent),recent_acc=kr/len(recent) if len(recent) else np.nan,recent_lo=LR))
r=pd.DataFrame(rows)
print(r.sort_values(['accuracy','n'],ascending=[False,False]).head(120).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),coverage=lambda x:(100*x.coverage).round(2),recent_acc=lambda x:(100*x.recent_acc).round(2),recent_lo=lambda x:(100*x.recent_lo).round(2)).to_string(index=False))

# Fixed interpretable intraday patterns, locked first half vs 2026 holdout.
# thresholds derived from training only.
train=df[df.ts<pd.Timestamp('2026-01-01',tz='UTC')].copy();hold=df[df.ts>=pd.Timestamp('2026-01-01',tz='UTC')].copy()
thresholds={f:(train[f].quantile(.1),train[f].quantile(.9)) for f in ['ret1','ret3','range_atr','volratio','body_atr']}
def pats(z):
 p={}
 p['large_up_close_high']=(z.ret1>=thresholds['ret1'][1])&(z.clv>.7)
 p['large_dn_close_low']=(z.ret1<=thresholds['ret1'][0])&(z.clv<-.7)
 p['up3_break24']=(z.ret3>0)&(z.breakhi24>0)
 p['dn3_break24']=(z.ret3<0)&(z.breaklo24>0)
 p['compression_uptrend']=(z.volratio<.7)&(z.ret12>0)&(z.magap24>0)
 p['compression_dntrend']=(z.volratio<.7)&(z.ret12<0)&(z.magap24<0)
 p['rsi3_low']=z.rsi3<10;p['rsi3_high']=z.rsi3>90
 p['lowerwick_rsi_low']=(z.lowerwick>1)&(z.rsi6<25);p['upperwick_rsi_high']=(z.upperwick>1)&(z.rsi6>75)
 p['london_large_up']=(z.london>0)&(z.ret1>=thresholds['ret1'][1]);p['london_large_dn']=(z.london>0)&(z.ret1<=thresholds['ret1'][0])
 p['ny_large_up']=(z.ny>0)&(z.ret1>=thresholds['ret1'][1]);p['ny_large_dn']=(z.ny>0)&(z.ret1<=thresholds['ret1'][0])
 return p
pt=pats(train);ph=pats(hold)
print('\n=== LOCKED 2026 INTRADAY PATTERNS ===')
rr=[]
for name,mt in pt.items():
 for h in [1,2,3,6,12]:
  st=train.loc[mt.fillna(False),f'fret{h}'].dropna();ntr=len(st)
  if ntr<50:continue
  up=float((st>0).mean());d=1 if up>=.5 else 0;tracc=max(up,1-up)
  sh=hold.loc[ph[name].fillna(False),f'fret{h}'].dropna();n=len(sh)
  if n<15:continue
  k=int((sh>0).sum()) if d else int((sh<0).sum());acc=k/n;L,U=wilson(k,n)
  rr.append(dict(pattern=name,h=h,train_n=ntr,train_acc=tracc,dir='UP' if d else 'DOWN',n=n,hold_acc=acc,wilson_lo=L,median=float(sh.median())))
rr=pd.DataFrame(rr)
print(rr.sort_values(['hold_acc','n'],ascending=[False,False]).head(100).assign(train_acc=lambda x:(100*x.train_acc).round(2),hold_acc=lambda x:(100*x.hold_acc).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),median=lambda x:(100*x['median']).round(3)).to_string(index=False))

print('\n=== INTRADAY 75 N>=30 CHECK ===')
print('models',len(r[(r.accuracy>=.75)&(r.n>=30)]),'locked',len(rr[(rr.hold_acc>=.75)&(rr.n>=30)]))
