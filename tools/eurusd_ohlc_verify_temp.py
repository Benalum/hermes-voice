import requests,math
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier,ExtraTreesClassifier

P1=int(pd.Timestamp('2006-01-01',tz='UTC').timestamp());P2=int(pd.Timestamp('2026-08-17',tz='UTC').timestamp())
u=f'https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X?period1={P1}&period2={P2}&interval=1d&events=history'
r=requests.get(u,timeout=90,headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status();j=r.json()['chart']['result'][0];q=j['indicators']['quote'][0]
y=pd.DataFrame({'date':pd.to_datetime(j['timestamp'],unit='s',utc=True).tz_convert(None).normalize(),'open':q['open'],'high':q['high'],'low':q['low'],'close':q['close']}).dropna().sort_values('date').drop_duplicates('date').reset_index(drop=True)
print('YAHOO',len(y),y.date.min(),y.date.max())
y['nextclose']=y.close.shift(-1);inside=((y.nextclose>=y.low)&(y.nextclose<=y.high));print('NEXT_CLOSE_INSIDE_CURRENT_HILO_PCT',100*inside.mean())
print('OPEN_CLOSE_MEDIAN_ABS_PIPS',1e4*(y.open-y.close).abs().median(),'CLOSE_TO_NEXT_MEDIAN_ABS_PIPS',1e4*(y.nextclose-y.close).abs().median())

def features(df):
 z=df.copy();pc=z.close.shift(1);rng=(z.high-z.low);tr=pd.concat([rng,(z.high-pc).abs(),(z.low-pc).abs()],axis=1).max(axis=1);atr=tr.rolling(14).mean()
 z['ret1']=np.log(z.close).diff()
 raw={}
 raw['range_atr']=rng/atr;raw['body_atr']=(z.close-z.open)/atr;raw['absbody_atr']=(z.close-z.open).abs()/atr;raw['clv']=((z.close-z.low)-(z.high-z.close))/rng.replace(0,np.nan);raw['upperwick']=(z.high-z[['open','close']].max(axis=1))/atr;raw['lowerwick']=(z[['open','close']].min(axis=1)-z.low)/atr;raw['inside']=((z.high<z.high.shift())&(z.low>z.low.shift())).astype(float);raw['outside']=((z.high>z.high.shift())&(z.low<z.low.shift())).astype(float)
 for k,v in raw.items():z[k]=v.shift(1)
 for n in [2,3,5,10,20,50,100]:z[f'ret{n}']=np.log(z.close).diff(n)
 for n in [5,10,20,50]:
  ma=z.close.rolling(n).mean();sd=z.close.rolling(n).std();z[f'z{n}']=(z.close-ma)/sd;z[f'magap{n}']=z.close/ma-1
 ch=z.close.diff();up=ch.clip(lower=0);dn=(-ch.clip(upper=0))
 for n in [2,5,14]:
  rs=up.rolling(n).mean()/dn.rolling(n).mean().replace(0,np.nan);z[f'rsi{n}']=100-100/(1+rs)
 for n in [10,20,60]:
  hh=z.high.rolling(n).max().shift(1);ll=z.low.rolling(n).min().shift(1);z[f'donch{n}']=(z.close-ll)/(hh-ll)
 z['vol5']=z.ret1.rolling(5).std();z['vol20']=z.ret1.rolling(20).std();z['dow']=z.date.dt.weekday
 for h in [1,2,3,5]:z[f'fret{h}']=np.log(z.close.shift(-h)/z.close);z[f'y{h}']=(z[f'fret{h}']>0).astype(float);z.loc[z[f'fret{h}'].isna(),f'y{h}']=np.nan
 return z
Y=features(y)

def wilson(k,n,z=1.959963984540054):
 if n<=0:return np.nan,np.nan
 p=k/n;den=1+z*z/n;ctr=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;return ctr-half,ctr+half

def rules(z):return {'prev_upperwick_big':z.upperwick>1,'prev_lowerwick_big':z.lowerwick>1,'prev_clv_high':z.clv>.8,'prev_clv_low':z.clv<-.8,'prev_upperwick_.5':z.upperwick>.5,'prev_lowerwick_.5':z.lowerwick>.5,'rsi2_low':z.rsi2<10,'rsi2_high':z.rsi2>90}
print('\n=== CORRECTED COMPLETED-BAR RULES ===')
rows=[]
for name,mask in rules(Y).items():
 for spaced in [False,True]:
  idx=np.flatnonzero(mask.fillna(False));
  if spaced:
   keep=[];last=-99
   for i in idx:
    if i-last>=5:keep.append(i);last=i
   idx=np.array(keep,dtype=int)
  sub=Y.iloc[idx]
  for h in [1,2,3,5]:
   for period,ss in [('all',sub),('2022+',sub[sub.date>=pd.Timestamp('2022-01-01')]),('2024+',sub[sub.date>=pd.Timestamp('2024-01-01')])]:
    x=ss[f'fret{h}'].dropna();n=len(x)
    if n<10:continue
    up=float((x>0).mean());d='UP' if up>=.5 else 'DOWN';k=int((x>0).sum()) if d=='UP' else int((x<0).sum());acc=k/n;L,U=wilson(k,n);rows.append(dict(rule=name,spaced=spaced,h=h,period=period,n=n,direction=d,accuracy=acc,wilson_lo=L,median=float(x.median())))
rr=pd.DataFrame(rows);print(rr.sort_values(['accuracy','n'],ascending=[False,False]).head(120).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),median=lambda x:(100*x['median']).round(3)).to_string(index=False))

FEATURES=['ret1','range_atr','body_atr','absbody_atr','clv','upperwick','lowerwick','inside','outside','ret2','ret3','ret5','ret10','ret20','ret50','ret100','z5','z10','z20','z50','magap5','magap10','magap20','magap50','rsi2','rsi5','rsi14','donch10','donch20','donch60','vol5','vol20','dow']
def models():return {'logit':Pipeline([('i',SimpleImputer(strategy='median')),('s',StandardScaler()),('m',LogisticRegression(C=.2,max_iter=1500))]),'hgb':Pipeline([('i',SimpleImputer(strategy='median')),('m',HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=10,min_samples_leaf=40,learning_rate=.04,l2_regularization=4,random_state=9))]),'extra':Pipeline([('i',SimpleImputer(strategy='median')),('m',ExtraTreesClassifier(n_estimators=300,max_depth=7,min_samples_leaf=25,max_features=.55,class_weight='balanced',random_state=9,n_jobs=-1))])}
print('\n=== CORRECTED YAHOO-ONLY WALK FORWARD ===')
rows=[]
for h in [1,2,3,5]:
 pieces=[];target=f'y{h}'
 for year in range(2014,2027):
  tr=Y[(Y.date<pd.Timestamp(f'{year}-01-01'))&Y[target].notna()];te=Y[(Y.date>=pd.Timestamp(f'{year}-01-01'))&(Y.date<pd.Timestamp(f'{year+1}-01-01'))&Y[target].notna()]
  if len(tr)<1200 or not len(te):continue
  P=[]
  for m in models().values():m.fit(tr[FEATURES],tr[target].astype(int));P.append(m.predict_proba(te[FEATURES])[:,1])
  P=np.vstack(P);pieces.append(pd.DataFrame({'date':te.date.values,'y':te[target].astype(int).values,'p':P.mean(0),'spread':P.max(0)-P.min(0)}))
 pr=pd.concat(pieces,ignore_index=True)
 for t in [.5,.525,.55,.575,.60,.625,.65,.675,.70,.725,.75]:
  for ag in [False,True]:
   use=(pr.p>=t)|(pr.p<=1-t)
   if ag:use&=pr.spread<=.10
   z=pr[use];n=len(z)
   if not n:continue
   k=int((((z.p>=.5).astype(int))==z.y).sum());acc=k/n;L,U=wilson(k,n);recent=z[pd.to_datetime(z.date)>=pd.Timestamp('2022-01-01')];kr=int((((recent.p>=.5).astype(int))==recent.y).sum()) if len(recent) else 0;LR,UR=wilson(kr,len(recent)) if len(recent) else (np.nan,np.nan)
   rows.append(dict(h=h,t=t,agree=ag,n=n,accuracy=acc,wilson_lo=L,recent_n=len(recent),recent_acc=kr/len(recent) if len(recent) else np.nan,recent_lo=LR))
mod=pd.DataFrame(rows);print(mod.sort_values(['accuracy','n'],ascending=[False,False]).head(100).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),recent_acc=lambda x:(100*x.recent_acc).round(2),recent_lo=lambda x:(100*x.recent_lo).round(2)).to_string(index=False))
print('\n=== CORRECTED VERIFIED 75 CHECK ===');print('rules_n>=30',len(rr[(rr.accuracy>=.75)&(rr.n>=30)]),'model_n>=30',len(mod[(mod.accuracy>=.75)&(mod.n>=30)]))
