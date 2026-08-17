import runpy, io, math, time
import numpy as np
import pandas as pd
import requests
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score

ns=runpy.run_path('tools/cot_eurusd_backtest_refine_temp.py')
base=ns['df'].copy()

# Try Stooq OHLC, fallback to Yahoo chart API.
def get_ohlc():
    urls=['https://stooq.com/q/d/l/?s=eurusd&i=d&d1=20060101&d2=20260816']
    for u in urls:
        try:
            r=requests.get(u,timeout=60,headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status()
            z=pd.read_csv(io.StringIO(r.text)); cols={c.lower():c for c in z.columns}
            if all(k in cols for k in ['date','open','high','low','close']) and len(z)>1000:
                o=z.rename(columns={cols['date']:'date',cols['open']:'open',cols['high']:'high',cols['low']:'low',cols['close']:'close'})[['date','open','high','low','close']]
                o.date=pd.to_datetime(o.date); return o.sort_values('date').drop_duplicates('date')
        except Exception as e: print('STOOQ_FAIL',repr(e))
    # Yahoo fallback
    import datetime as dt
    p1=int(pd.Timestamp('2006-01-01',tz='UTC').timestamp());p2=int(pd.Timestamp('2026-08-17',tz='UTC').timestamp())
    u=f'https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X?period1={p1}&period2={p2}&interval=1d&events=history'
    r=requests.get(u,timeout=60,headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status();j=r.json()['chart']['result'][0]
    ts=pd.to_datetime(j['timestamp'],unit='s',utc=True).tz_convert(None).normalize();q=j['indicators']['quote'][0]
    return pd.DataFrame({'date':ts,'open':q['open'],'high':q['high'],'low':q['low'],'close':q['close']}).dropna().sort_values('date').drop_duplicates('date')

o=get_ohlc(); print('OHLC_SOURCE_ROWS',len(o),o.date.min(),o.date.max())
# Merge with macro dataset; use OHLC close as price features, base macro/COT features only from same/prior date.
df=o.merge(base.drop(columns=['eurusd'],errors='ignore'),on='date',how='inner').sort_values('date').reset_index(drop=True)
df['eurusd']=df['close']

# Price/candle features.
pc=df.close.shift(1); tr=pd.concat([(df.high-df.low),(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1)
atr14=tr.rolling(14).mean(); rng=(df.high-df.low).replace(0,np.nan)
df['logret1']=np.log(df.close).diff()
df['gap']=np.log(df.open/pc)
df['range_atr']=(df.high-df.low)/atr14
df['body_atr']=(df.close-df.open)/atr14
df['absbody_atr']=(df.close-df.open).abs()/atr14
df['clv']=((df.close-df.low)-(df.high-df.close))/rng
df['upper_wick']= (df.high-df[['open','close']].max(axis=1))/atr14
df['lower_wick']= (df[['open','close']].min(axis=1)-df.low)/atr14
df['doji']=((df.close-df.open).abs()/rng<.15).astype(float)
df['inside']=((df.high<df.high.shift(1))&(df.low>df.low.shift(1))).astype(float)
df['outside']=((df.high>df.high.shift(1))&(df.low<df.low.shift(1))).astype(float)
df['bull_engulf']=((df.close>df.open)&(df.close.shift(1)<df.open.shift(1))&(df.close>=df.open.shift(1))&(df.open<=df.close.shift(1))).astype(float)
df['bear_engulf']=((df.close<df.open)&(df.close.shift(1)>df.open.shift(1))&(df.open>=df.close.shift(1))&(df.close<=df.open.shift(1))).astype(float)
for n in [2,3,5,10,20,50,100]:df[f'pxret{n}']=np.log(df.close).diff(n)
for n in [5,10,20,50]:
    ma=df.close.rolling(n).mean();sd=df.close.rolling(n).std();df[f'magap{n}']=df.close/ma-1;df[f'z{n}']=(df.close-ma)/sd
for n in [4,7]:
    rr=(df.high-df.low);df[f'nr{n}']=(rr<=rr.rolling(n).min()).astype(float)
for n in [10,20,60]:
    hh=df.high.rolling(n).max().shift(1);ll=df.low.rolling(n).min().shift(1)
    df[f'donch{n}']=(df.close-ll)/(hh-ll)
    df[f'breakhi{n}']=(df.close>hh).astype(float);df[f'breaklo{n}']=(df.close<ll).astype(float)
# RSI helper
chg=df.close.diff();up=chg.clip(lower=0);dn=(-chg.clip(upper=0))
for n in [2,5,14]:
    rs=up.rolling(n).mean()/dn.rolling(n).mean().replace(0,np.nan);df[f'rsi{n}']=100-100/(1+rs)
# stochastic
ll=df.low.rolling(14).min();hh=df.high.rolling(14).max();df['stoch14']=100*(df.close-ll)/(hh-ll)
# ATR and volatility
for n in [5,14,20]:df[f'atrpct{n}']=tr.rolling(n).mean()/df.close
# Consecutive direction counts
sign=np.sign(df.logret1.fillna(0));
def streak_at(i):
    if i==0:return 0
    s=sign.iloc[i];
    if s==0:return 0
    k=0;j=i
    while j>=0 and sign.iloc[j]==s and k<10:k+=1;j-=1
    return s*k
df['streak']=[streak_at(i) for i in range(len(df))]

# Recompute targets from OHLC close.
for h in [1,2,3,5]:
    df[f'fret{h}']=np.log(df.close.shift(-h)/df.close);df[f'y{h}']=(df[f'fret{h}']>0).astype(float);df.loc[df[f'fret{h}'].isna(),f'y{h}']=np.nan

OHLC=['gap','range_atr','body_atr','absbody_atr','clv','upper_wick','lower_wick','doji','inside','outside','bull_engulf','bear_engulf',
      'pxret2','pxret3','pxret5','pxret10','pxret20','pxret50','pxret100','magap5','magap10','magap20','magap50','z5','z10','z20','z50',
      'nr4','nr7','donch10','donch20','donch60','breakhi10','breakhi20','breakhi60','breaklo10','breaklo20','breaklo60','rsi2','rsi5','rsi14','stoch14','atrpct5','atrpct14','atrpct20','streak']
MACRO=['dgs2_chg1','dgs2_chg5','dgs2_chg20','dgs10_chg5','curve','curve_chg5','policy_spread','policy_spread_chg20','usd_ret5','usd_ret20','brent_ret5','brent_ret20','vix_chg5','vix_z60','asset_net_pct_oi','lev_net_pct_oi','dealer_net_pct_oi','lev_chg4','asset_chg4']
FEATURES=OHLC+MACRO

# Models and expanding annual walk-forward.
def models():
 return {
  'logit':Pipeline([('imp',SimpleImputer(strategy='median')),('sc',StandardScaler()),('m',LogisticRegression(C=.2,max_iter=2000))]),
  'hgb':Pipeline([('imp',SimpleImputer(strategy='median')),('m',HistGradientBoostingClassifier(max_iter=120,learning_rate=.04,max_leaf_nodes=10,min_samples_leaf=40,l2_regularization=4,random_state=11))]),
  'extra':Pipeline([('imp',SimpleImputer(strategy='median')),('m',ExtraTreesClassifier(n_estimators=350,max_depth=6,min_samples_leaf=25,max_features=.55,class_weight='balanced',random_state=11,n_jobs=-1))])
 }

def wilson(k,n,z=1.959963984540054):
 if n<=0:return np.nan,np.nan
 p=k/n;den=1+z*z/n;ctr=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;return ctr-half,ctr+half

allpred={}
for h in [1,2,3,5]:
 target=f'y{h}';pieces=[]
 for year in range(2014,2027):
  trn=df[(df.date<pd.Timestamp(f'{year}-01-01'))&df[target].notna()];tst=df[(df.date>=pd.Timestamp(f'{year}-01-01'))&(df.date<pd.Timestamp(f'{year+1}-01-01'))&df[target].notna()]
  if len(trn)<1200 or not len(tst):continue
  ms=models();ps=[]
  for name,m in ms.items():m.fit(trn[FEATURES],trn[target].astype(int));ps.append(m.predict_proba(tst[FEATURES])[:,1])
  P=np.vstack(ps);p=P.mean(axis=0);spread=P.max(axis=0)-P.min(axis=0)
  pieces.append(pd.DataFrame({'date':tst.date.values,'y':tst[target].astype(int).values,'p':p,'p_logit':P[0],'p_hgb':P[1],'p_extra':P[2],'spread':spread}))
 allpred[h]=pd.concat(pieces,ignore_index=True).sort_values('date')

print('=== OHLC WALK FORWARD SELECTIVE ===')
rows=[]
for h,pr in allpred.items():
 for t in [.50,.525,.55,.575,.60,.625,.65,.675,.70,.725,.75]:
  for agreement in [False,True]:
   use=((pr.p>=t)|(pr.p<=1-t))
   if agreement: use &= (pr.spread<=.12)
   q=pr[use];n=len(q)
   if not n:continue
   pred=(q.p>=.5).astype(int);k=int((pred==q.y).sum());L,U=wilson(k,n)
   recent=q[pd.to_datetime(q.date)>=pd.Timestamp('2022-01-01')];kr=int((((recent.p>=.5).astype(int))==recent.y).sum()) if len(recent) else 0;LR,UR=wilson(kr,len(recent)) if len(recent) else (np.nan,np.nan)
   rows.append(dict(h=h,t=t,agree=agreement,n=n,accuracy=k/n,wilson_lo=L,coverage=n/len(pr),recent_n=len(recent),recent_acc=kr/len(recent) if len(recent) else np.nan,recent_lo=LR))
r=pd.DataFrame(rows)
print(r.sort_values(['accuracy','n'],ascending=[False,False]).head(100).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),coverage=lambda x:(100*x.coverage).round(2),recent_acc=lambda x:(100*x.recent_acc).round(2),recent_lo=lambda x:(100*x.recent_lo).round(2)).to_string(index=False))

# Candlestick-specific fixed rules to see if any simple patterns are robust.
conds={
 'rsi2_low':df.rsi2<10,'rsi2_high':df.rsi2>90,'rsi5_low':df.rsi5<20,'rsi5_high':df.rsi5>80,
 'nr7':df.nr7>0,'inside':df.inside>0,'outside':df.outside>0,'bull_engulf':df.bull_engulf>0,'bear_engulf':df.bear_engulf>0,
 'lowerwick_big':df.lower_wick>1,'upperwick_big':df.upper_wick>1,'clv_high':df.clv>.8,'clv_low':df.clv<-.8,
 'breakhi20':df.breakhi20>0,'breaklo20':df.breaklo20>0,'z20_high':df.z20>1.5,'z20_low':df.z20<-1.5,
 'streak_up3':df.streak>=3,'streak_dn3':df.streak<=-3,'streak_up4':df.streak>=4,'streak_dn4':df.streak<=-4,
}
print('\n=== OHLC SIMPLE PATTERNS ===')
rr=[]
for name,m in conds.items():
 idx=np.flatnonzero(m.fillna(False));keep=[];last=-99
 for i in idx:
  if i-last>=5:keep.append(i);last=i
 sub=df.iloc[keep]
 for h in [1,2,3,5]:
  s=sub[f'fret{h}'].dropna();n=len(s)
  if n<20:continue
  up=float((s>0).mean());d='UP' if up>=.5 else 'DOWN';k=int((s>0).sum()) if d=='UP' else int((s<0).sum());acc=k/n;L,U=wilson(k,n)
  rr.append(dict(pattern=name,h=h,n=n,direction=d,accuracy=acc,wilson_lo=L,median=float(s.median())))
rr=pd.DataFrame(rr)
print(rr.sort_values(['accuracy','n'],ascending=[False,False]).head(80).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),median=lambda x:(100*x['median']).round(3)).to_string(index=False))

print('\n=== OHLC 75 N>=30 CHECK ===')
print('model',len(r[(r.accuracy>=.75)&(r.n>=30)]),'simple',len(rr[(rr.accuracy>=.75)&(rr.n>=30)]))
