import io, json, math, time
import numpy as np
import pandas as pd
import requests
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score, brier_score_loss

START='2006-01-01'
END='2026-08-16'
HORIZONS=[1,5,10]

# ---------- data helpers ----------
def get_csv(url, tries=4):
    last=None
    for i in range(tries):
        try:
            r=requests.get(url,timeout=90); r.raise_for_status(); return r.text
        except Exception as e:
            last=e; time.sleep(1.5*(i+1))
    raise last

def fred(series):
    url=f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={START}&coed={END}'
    x=pd.read_csv(io.StringIO(get_csv(url)))
    x.columns=['date',series.lower()]
    x['date']=pd.to_datetime(x['date'])
    x[series.lower()]=pd.to_numeric(x[series.lower()],errors='coerce')
    return x.sort_values('date')

series=['DEXUSEU','DGS2','DGS10','DFF','ECBDFR','DTWEXBGS','DCOILBRENTEU','VIXCLS']
frames={s:fred(s) for s in series}
df=frames['DEXUSEU'].rename(columns={'dexuseu':'eurusd'}).copy()
for s in series[1:]:
    df=df.merge(frames[s],on='date',how='left')
# Keep only FX observation dates; carry other already-published series forward.
for c in [s.lower() for s in series[1:]]:
    df[c]=df[c].ffill()
df=df.dropna(subset=['eurusd']).sort_values('date').reset_index(drop=True)

# ---------- CFTC TFF futures-only ----------
url='https://publicreporting.cftc.gov/resource/gpe5-46if.json'
params={'$limit':'50000','$order':'report_date_as_yyyy_mm_dd ASC','$where':"cftc_contract_market_code='099741'"}
r=requests.get(url,params=params,timeout=90); r.raise_for_status(); rows=r.json()
if not rows: raise RuntimeError('No CFTC Euro FX rows')
keys=set().union(*(z.keys() for z in rows[:30]))
def fld(*xs):
    for x in xs:
        if x in keys:return x
    raise KeyError(xs)
fd=fld('report_date_as_yyyy_mm_dd'); foi=fld('open_interest_all')
fal=fld('asset_mgr_positions_long','asset_mgr_positions_long_all'); fas=fld('asset_mgr_positions_short','asset_mgr_positions_short_all')
fll=fld('lev_money_positions_long_all','lev_money_positions_long'); fls=fld('lev_money_positions_short_all','lev_money_positions_short')
fdl=fld('dealer_positions_long_all','dealer_positions_long'); fds=fld('dealer_positions_short_all','dealer_positions_short')
rec=[]
for z in rows:
    try:
        rec.append({'report_date':pd.to_datetime(z[fd]).tz_localize(None),'oi':float(z[foi]),
                    'asset_net':float(z[fal])-float(z[fas]),
                    'lev_net':float(z[fll])-float(z[fls]),
                    'dealer_net':float(z[fdl])-float(z[fds])})
    except Exception: pass
cot=pd.DataFrame(rec).drop_duplicates('report_date').sort_values('report_date').reset_index(drop=True)
for c in ['asset','lev','dealer']:
    cot[f'{c}_net_pct_oi']=cot[f'{c}_net']/cot.oi
cot['lev_chg4']=cot.lev_net_pct_oi.diff(4)
cot['asset_chg4']=cot.asset_net_pct_oi.diff(4)
# Conservative historical availability: Tuesday report is used from following Monday onward.
# Exclude the abnormal 2025 shutdown/catch-up block used in the prior audit.
cot=cot[~cot.report_date.between(pd.Timestamp('2025-09-30'),pd.Timestamp('2026-01-13'))].copy()
cot['effective_date']=cot.report_date+pd.Timedelta(days=6)
cfeat=cot[['effective_date','report_date','asset_net_pct_oi','lev_net_pct_oi','dealer_net_pct_oi','lev_chg4','asset_chg4']].sort_values('effective_date')
df=pd.merge_asof(df.sort_values('date'),cfeat,left_on='date',right_on='effective_date',direction='backward')

# ---------- feature engineering ----------
px=df.eurusd
logpx=np.log(px)
df['ret1']=logpx.diff(1)
for n in [5,20,60]: df[f'ret{n}']=logpx.diff(n)
for n in [20,50,100]: df[f'ma{n}_gap']=px/px.rolling(n).mean()-1
df['vol10']=df.ret1.rolling(10).std()*np.sqrt(252)
df['vol20']=df.ret1.rolling(20).std()*np.sqrt(252)
df['dgs2_chg1']=df.dgs2.diff(1); df['dgs2_chg5']=df.dgs2.diff(5); df['dgs2_chg20']=df.dgs2.diff(20)
df['dgs10_chg5']=df.dgs10.diff(5); df['curve']=df.dgs10-df.dgs2; df['curve_chg5']=df['curve'].diff(5)
df['policy_spread']=df.dff-df.ecbdfr; df['policy_spread_chg20']=df.policy_spread.diff(20)
df['usd_ret5']=np.log(df.dtwexbgs).diff(5); df['usd_ret20']=np.log(df.dtwexbgs).diff(20)
df['brent_ret5']=np.log(df.dcoilbrenteu).diff(5); df['brent_ret20']=np.log(df.dcoilbrenteu).diff(20)
df['vix_chg5']=df.vixcls.diff(5); df['vix_z60']=(df.vixcls-df.vixcls.rolling(60).mean())/df.vixcls.rolling(60).std()
for h in HORIZONS:
    df[f'fret{h}']=np.log(df.eurusd.shift(-h)/df.eurusd)
    df[f'y{h}']=(df[f'fret{h}']>0).astype(float)
    df.loc[df[f'fret{h}'].isna(),f'y{h}']=np.nan

FEATURES=['ret1','ret5','ret20','ret60','ma20_gap','ma50_gap','ma100_gap','vol10','vol20',
          'dgs2_chg1','dgs2_chg5','dgs2_chg20','dgs10_chg5','curve','curve_chg5',
          'policy_spread','policy_spread_chg20','usd_ret5','usd_ret20','brent_ret5','brent_ret20',
          'vix_chg5','vix_z60','asset_net_pct_oi','lev_net_pct_oi','dealer_net_pct_oi','lev_chg4','asset_chg4']

# ---------- transparent rule tests ----------
def rule_signs(x):
    out=pd.DataFrame(index=x.index)
    out['mom20']=np.where(x.ret20>=0,1,-1)
    out['ma50']=np.where(x.ma50_gap>=0,1,-1)
    out['us2y_5d']=np.where(x.dgs2_chg5<=0,1,-1)             # falling US front-end yield -> EUR+
    out['broad_usd_5d']=np.where(x.usd_ret5<=0,1,-1)        # falling broad USD -> EUR+
    out['policy_spread_20d']=np.where(x.policy_spread_chg20<=0,1,-1)
    out['cot_4w']=np.where(x.lev_chg4>=0,1,-1)              # leveraged funds becoming less bearish -> EUR+
    out['risk_5d']=np.where(x.vix_chg5<=0,1,-1)
    votes=(out[['mom20','us2y_5d','broad_usd_5d','policy_spread_20d','cot_4w','risk_5d']]>0).sum(axis=1)
    out['composite6']=np.where(votes>=3,1,-1)
    return out
rules=rule_signs(df)
rule_rows=[]
for h in HORIZONS:
    valid=df[f'fret{h}'].notna() & (df.date>=pd.Timestamp('2010-01-01'))
    actual=np.sign(df.loc[valid,f'fret{h}']).replace(0,np.nan)
    for c in rules.columns:
        sig=rules.loc[valid,c]
        ok=actual.notna() & sig.notna()
        signed=sig[ok]*df.loc[valid,f'fret{h}'][ok]
        rule_rows.append({'rule':c,'h':h,'n':int(ok.sum()),'accuracy':float((sig[ok]==actual[ok]).mean()),
                          'mean_signed_ret':float(signed.mean()),'median_signed_ret':float(signed.median())})
rule_table=pd.DataFrame(rule_rows)

# ---------- expanding walk-forward models ----------
def make_logit():
    return Pipeline([('imp',SimpleImputer(strategy='median')),('sc',StandardScaler()),
                     ('m',LogisticRegression(C=0.3,max_iter=2000,class_weight=None,random_state=7))])
def make_hgb():
    return Pipeline([('imp',SimpleImputer(strategy='median')),
                     ('m',HistGradientBoostingClassifier(max_iter=120,learning_rate=.05,max_leaf_nodes=12,
                                                        min_samples_leaf=35,l2_regularization=2.0,random_state=7))])

preds={}
metrics=[]
for h in HORIZONS:
    target=f'y{h}'
    allpred=[]
    for year in range(2014,2027):
        train=df[(df.date<pd.Timestamp(f'{year}-01-01')) & df[target].notna()].copy()
        test=df[(df.date>=pd.Timestamp(f'{year}-01-01')) & (df.date<pd.Timestamp(f'{year+1}-01-01')) & df[target].notna()].copy()
        if len(train)<1200 or len(test)==0: continue
        logit=make_logit(); hgb=make_hgb()
        logit.fit(train[FEATURES],train[target].astype(int)); hgb.fit(train[FEATURES],train[target].astype(int))
        p1=logit.predict_proba(test[FEATURES])[:,1]; p2=hgb.predict_proba(test[FEATURES])[:,1]
        p=.6*p1+.4*p2
        q=pd.DataFrame({'date':test.date.values,'y':test[target].astype(int).values,'p':p,'p_logit':p1,'p_hgb':p2})
        allpred.append(q)
    pr=pd.concat(allpred,ignore_index=True).sort_values('date'); preds[h]=pr
    for label,sub in [('daily',pr),('wednesday',pr[pd.to_datetime(pr.date).dt.weekday==2])]:
        y=sub.y.values; p=sub.p.values; yh=(p>=.5).astype(int)
        metrics.append({'h':h,'sample':label,'n':len(sub),'accuracy':accuracy_score(y,yh),
                        'always_up':float(y.mean()),'auc':roc_auc_score(y,p),'brier':brier_score_loss(y,p)})
metrics=pd.DataFrame(metrics)

# ---------- current model state ----------
latest=df.dropna(subset=['eurusd']).iloc[-1:].copy()
latest_date=latest.date.iloc[0]
# COT is public Friday; for Sunday inference use the newest published report directly if newer than conservative Monday mapping.
latest_cot=cot.sort_values('report_date').iloc[-1]
for c in ['asset_net_pct_oi','lev_net_pct_oi','dealer_net_pct_oi','lev_chg4','asset_chg4']:
    latest.loc[latest.index,c]=float(latest_cot[c])
current_probs={}
coefs={}
for h in HORIZONS:
    train=df[df[f'y{h}'].notna()].copy()
    lg=make_logit(); hg=make_hgb(); lg.fit(train[FEATURES],train[f'y{h}'].astype(int)); hg.fit(train[FEATURES],train[f'y{h}'].astype(int))
    p1=float(lg.predict_proba(latest[FEATURES])[:,1][0]); p2=float(hg.predict_proba(latest[FEATURES])[:,1][0]); p=.6*p1+.4*p2
    current_probs[h]={'ensemble_up':p,'logit_up':p1,'hgb_up':p2}
    coef=lg.named_steps['m'].coef_[0]
    coefs[h]=sorted(zip(FEATURES,coef),key=lambda z:abs(z[1]),reverse=True)[:8]

current_rules=rule_signs(latest).iloc[0].to_dict()

# ---------- nearest historical analogues to current feature state ----------
ANALOG_FEATURES=['ret5','ret20','ma50_gap','dgs2_chg5','dgs2_chg20','policy_spread','policy_spread_chg20',
                 'usd_ret5','usd_ret20','brent_ret20','vix_z60','asset_net_pct_oi','lev_net_pct_oi','dealer_net_pct_oi','lev_chg4']
hist=df[(df.date<latest_date-pd.Timedelta(days=180)) & (df.date>=pd.Timestamp('2010-01-01'))].copy()
med=hist[ANALOG_FEATURES].median(); sd=hist[ANALOG_FEATURES].std().replace(0,np.nan)
H=((hist[ANALOG_FEATURES].fillna(med)-med)/sd).replace([np.inf,-np.inf],np.nan).fillna(0)
C=((latest[ANALOG_FEATURES].fillna(med)-med)/sd).replace([np.inf,-np.inf],np.nan).fillna(0).iloc[0]
hist['distance']=np.sqrt(((H-C)**2).sum(axis=1))
# Enforce spacing so one regime is not counted repeatedly.
analogs=[]
for _,row in hist.sort_values('distance').iterrows():
    if all(abs((row.date-a.date).days)>=30 for a in analogs):
        analogs.append(row)
    if len(analogs)>=20: break
analog=pd.DataFrame(analogs)
analog_summary={}
for h in HORIZONS:
    s=analog[f'fret{h}'].dropna()
    analog_summary[h]={'n':int(len(s)),'up_rate':float((s>0).mean()),'mean_ret':float(s.mean()),'median_ret':float(s.median()),
                       'q25':float(s.quantile(.25)),'q75':float(s.quantile(.75))}

# ---------- print compact research output ----------
pd.set_option('display.width',220); pd.set_option('display.max_columns',30)
print('DATA_RANGE',df.date.min().date(),latest_date.date(),'ROWS',len(df),'LATEST_EURUSD',float(latest.eurusd.iloc[0]))
print('LATEST_COT_REPORT',latest_cot.report_date.date(),'ASSET_NET_OI',float(latest_cot.asset_net_pct_oi),'LEV_NET_OI',float(latest_cot.lev_net_pct_oi),'DEALER_NET_OI',float(latest_cot.dealer_net_pct_oi))
print('\nRULE_BACKTEST')
print(rule_table.assign(accuracy=lambda x:(100*x.accuracy).round(2),mean_signed_ret=lambda x:(100*x.mean_signed_ret).round(3),median_signed_ret=lambda x:(100*x.median_signed_ret).round(3)).to_string(index=False))
print('\nWALK_FORWARD_METRICS')
print(metrics.assign(accuracy=lambda x:(100*x.accuracy).round(2),always_up=lambda x:(100*x.always_up).round(2),auc=lambda x:x.auc.round(3),brier=lambda x:x.brier.round(3)).to_string(index=False))
print('\nCURRENT_FEATURES')
for c in ['eurusd','ret5','ret20','ret60','ma20_gap','ma50_gap','dgs2','dgs2_chg5','dgs2_chg20','policy_spread','policy_spread_chg20','usd_ret5','usd_ret20','brent_ret20','vixcls','vix_chg5','asset_net_pct_oi','lev_net_pct_oi','lev_chg4']:
    print(c,float(latest[c].iloc[0]) if pd.notna(latest[c].iloc[0]) else None)
print('CURRENT_RULES',json.dumps({k:int(v) for k,v in current_rules.items()}))
print('CURRENT_MODEL_PROBS',json.dumps(current_probs))
print('TOP_LOGIT_COEFS',json.dumps({str(k):[(a,float(b)) for a,b in v] for k,v in coefs.items()}))
print('\nANALOGS')
print(analog[['date','distance','eurusd']+[f'fret{h}' for h in HORIZONS]].to_string(index=False))
print('ANALOG_SUMMARY',json.dumps(analog_summary))

result={'range':[str(df.date.min().date()),str(latest_date.date())],'latest_eurusd':float(latest.eurusd.iloc[0]),
        'latest_cot_report':str(latest_cot.report_date.date()),'rule_backtest':rule_table.to_dict('records'),
        'walk_forward':metrics.to_dict('records'),'current_probs':current_probs,'current_rules':{k:int(v) for k,v in current_rules.items()},
        'analog_summary':analog_summary,'top_logit_coefs':{str(k):[(a,float(b)) for a,b in v] for k,v in coefs.items()}}
print('\nRESULT_JSON='+json.dumps(result,separators=(',',':')))
