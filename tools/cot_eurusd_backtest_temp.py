import io, math, json
import numpy as np
import pandas as pd
import requests

TODAY = pd.Timestamp('2026-08-13')
HORIZONS = [1, 2, 4, 8, 13]

# Official CFTC TFF futures-only Socrata dataset. EUR FX contract market code = 099741.
url = 'https://publicreporting.cftc.gov/resource/gpe5-46if.json'
params = {'$limit': '50000', '$order': 'report_date_as_yyyy_mm_dd ASC', '$where': "cftc_contract_market_code='099741'"}
r = requests.get(url, params=params, timeout=90); r.raise_for_status(); rows = r.json()
if not rows:
    params['$where'] = "upper(market_and_exchange_names) like '%EURO FX%'"
    r = requests.get(url, params=params, timeout=90); r.raise_for_status(); rows = r.json()
if not rows: raise RuntimeError('CFTC returned no Euro FX rows')

keys = set().union(*(x.keys() for x in rows[:20]))
def fld(*cands):
    for c in cands:
        if c in keys: return c
    raise KeyError(f'Could not resolve {cands}; keys={sorted(keys)}')
fd=fld('report_date_as_yyyy_mm_dd'); foi=fld('open_interest_all')
fal=fld('asset_mgr_positions_long','asset_mgr_positions_long_all'); fas=fld('asset_mgr_positions_short','asset_mgr_positions_short_all')
fll=fld('lev_money_positions_long_all','lev_money_positions_long'); fls=fld('lev_money_positions_short_all','lev_money_positions_short')
fdl=fld('dealer_positions_long_all','dealer_positions_long'); fds=fld('dealer_positions_short_all','dealer_positions_short')

rec=[]
for x in rows:
    try:
        rec.append(dict(report_date=pd.to_datetime(x[fd]).tz_localize(None), oi=float(x[foi]),
                        asset_long=float(x[fal]), asset_short=float(x[fas]),
                        lev_long=float(x[fll]), lev_short=float(x[fls]),
                        dealer_long=float(x[fdl]), dealer_short=float(x[fds])))
    except (KeyError,TypeError,ValueError): pass
cot=pd.DataFrame(rec).drop_duplicates('report_date').sort_values('report_date').reset_index(drop=True)
for who in ['asset','lev','dealer']:
    cot[f'{who}_net']=cot[f'{who}_long']-cot[f'{who}_short']
    cot[f'{who}_net_pct_oi']=cot[f'{who}_net']/cot.oi
cot['lev_pctile_full']=cot.lev_net_pct_oi.rank(pct=True,method='average')
cot['signal']=(cot.asset_net>0)&(cot.lev_net<0)

# Official Fed H.10 EUR/USD, via FRED. COT normally publishes Friday for Tuesday positions,
# but holidays can delay release by 1-2 days. Use Wednesday of the following week
# (Tuesday + 8 calendar days) as a conservative release-safe entry date.
# Exclude the abnormal 2025 federal-shutdown catch-up block from outcome statistics.
fred='https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXUSEU&cosd=2006-01-01&coed=2026-08-13'
rr=requests.get(fred,timeout=90); rr.raise_for_status()
fx=pd.read_csv(io.StringIO(rr.text)); fx.columns=['date','eurusd']; fx.date=pd.to_datetime(fx.date); fx.eurusd=pd.to_numeric(fx.eurusd,errors='coerce'); fx=fx.dropna().sort_values('date').reset_index(drop=True)
def px_on_after(d,maxdays=5):
    i=fx.date.searchsorted(pd.Timestamp(d),'left')
    if i>=len(fx): return pd.NaT,np.nan
    dt=fx.iloc[i].date
    if dt>pd.Timestamp(d)+pd.Timedelta(days=maxdays): return pd.NaT,np.nan
    return dt,float(fx.iloc[i].eurusd)

shutdown_start=pd.Timestamp('2025-09-30')
shutdown_end=pd.Timestamp('2026-01-13')
out=[]
for _,q in cot.iterrows():
    ed,ep=px_on_after(q.report_date+pd.Timedelta(days=8))
    valid_release=not (shutdown_start <= q.report_date <= shutdown_end)
    z=q.to_dict(); z.update(entry_date=ed,entry_px=ep,valid_release=valid_release)
    for h in HORIZONS:
        dd,pp=px_on_after(ed+pd.Timedelta(days=7*h)) if pd.notna(ed) else (pd.NaT,np.nan)
        z[f'ret_{h}w']=pp/ep-1 if np.isfinite(ep) and np.isfinite(pp) else np.nan
    out.append(z)
bt=pd.DataFrame(out)
bt=bt[bt.valid_release].copy()

def wilson(k,n,z=1.959963984540054):
    if not n:return np.nan,np.nan
    p=k/n; den=1+z*z/n; ctr=(p+z*z/(2*n))/den; half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return ctr-half,ctr+half
def stats(df,h):
    s=df[f'ret_{h}w'].dropna(); n=len(s)
    if not n:return dict(n=0)
    k=int((s>0).sum()); lo,hi=wilson(k,n)
    return dict(n=n,up_rate=k/n,down_rate=float((s<0).mean()),mean=float(s.mean()),median=float(s.median()),ci_lo=lo,ci_hi=hi,q25=float(s.quantile(.25)),q75=float(s.quantile(.75)))

def summary(df):
    a=[]
    for h in HORIZONS:
        d=stats(df,h); d['horizon_weeks']=h; a.append(d)
    return pd.DataFrame(a)

sig=bt[bt.signal].copy()
main=summary(sig)
uncond=summary(bt)
main['uncond_up_rate']=uncond.up_rate.values; main['up_rate_edge']=main.up_rate-main.uncond_up_rate

ext=[]
for label,q in [('bottom25',.25),('bottom10',.10),('bottom5',.05)]:
    sub=sig[sig.lev_pctile_full<=q]
    s=summary(sub); s['bucket']=label; s['signal_rows']=len(sub); ext.append(s)
extreme=pd.concat(ext,ignore_index=True)

# One event per contiguous run of the condition, rather than counting a 10-week run 10 times.
sig=sig.sort_values('report_date')
sig['new_episode']=sig.report_date.diff().dt.days.fillna(999)>10
sig['episode_id']=sig.new_episode.cumsum().astype(int)
episodes=sig.groupby('episode_id',as_index=False).first() if len(sig) else sig
episode_summary=summary(episodes)
dealer_summary=summary(bt[(bt.asset_net>0)&(bt.lev_net<0)&(bt.dealer_net<0)])

current=cot[cot.report_date<=TODAY].iloc[-1]
# Nearest positioning analogues use net position / OI for scale invariance.
hist=cot[cot.report_date<current.report_date-pd.Timedelta(days=180)].copy(); cols=['asset_net_pct_oi','lev_net_pct_oi','dealer_net_pct_oi']
hist=hist[~hist.report_date.between(shutdown_start,shutdown_end)].copy()
hist[cols]=hist[cols].astype(float)
mu=hist[cols].mean(); sd=hist[cols].std(ddof=0).replace(0,np.nan)
cz=current[cols].astype(float).to_numpy(dtype=float); muz=mu.to_numpy(dtype=float); sdz=sd.to_numpy(dtype=float)
cur_z=(cz-muz)/sdz
hist_z=(hist[cols].to_numpy(dtype=float)-muz)/sdz
hist['distance']=np.sqrt(np.square(hist_z-cur_z).sum(axis=1))
analog_dates=hist.nsmallest(20,'distance')[['report_date','distance']]
analog=bt.merge(analog_dates,on='report_date',how='inner').sort_values('distance'); analog_summary=summary(analog)

curpct=float(current.lev_pctile_full)
similar=bt[(bt.report_date<current.report_date-pd.Timedelta(days=180))&(bt.asset_net>0)&(bt.dealer_net<0)&bt.lev_pctile_full.between(max(0,curpct-.05),min(1,curpct+.05))]
similar_summary=summary(similar)

def pct(df):
    y=df.copy()
    for c in ['up_rate','down_rate','mean','median','ci_lo','ci_hi','q25','q75','uncond_up_rate','up_rate_edge']:
        if c in y:y[c]*=100
    return y
pd.set_option('display.width',240); pd.set_option('display.max_columns',30); pd.set_option('display.float_format',lambda x:f'{x:.3f}')
print('DATA',len(cot),cot.report_date.min().date(),cot.report_date.max().date(),'BT_VALID_ROWS',len(bt),'FX',len(fx),fx.date.min().date(),fx.date.max().date())
print('SIGNAL_WEEKS_VALID',len(sig),'EPISODES',len(episodes))
print('\nMAIN_PCT\n'+pct(main).to_string(index=False))
print('\nEXTREME_PCT\n'+pct(extreme).to_string(index=False))
print('\nEPISODES_PCT\n'+pct(episode_summary).to_string(index=False))
print('\nDEALER_NEGATIVE_PCT\n'+pct(dealer_summary).to_string(index=False))
print('\nCURRENT\n'+current[['report_date','oi','asset_long','asset_short','asset_net','lev_long','lev_short','lev_net','dealer_long','dealer_short','dealer_net','asset_net_pct_oi','lev_net_pct_oi','dealer_net_pct_oi','lev_pctile_full']].to_string())
print('\nANALOGS\n'+analog[['report_date','distance','asset_net','lev_net','dealer_net']+[f'ret_{h}w' for h in HORIZONS]].to_string(index=False))
print('\nANALOG_SUMMARY_PCT\n'+pct(analog_summary).to_string(index=False))
print('\nSIMILAR_N',len(similar),'CURRENT_LEV_PERCENTILE',curpct)
print(pct(similar_summary).to_string(index=False))

payload={'range':[str(cot.report_date.min().date()),str(cot.report_date.max().date())],'signal_weeks_valid':int(len(sig)),'episodes':int(len(episodes)),
         'main':main.replace({np.nan:None}).to_dict('records'),'extreme':extreme.replace({np.nan:None}).to_dict('records'),'episode_summary':episode_summary.replace({np.nan:None}).to_dict('records'),
         'dealer_summary':dealer_summary.replace({np.nan:None}).to_dict('records'),'analog_summary':analog_summary.replace({np.nan:None}).to_dict('records'),'similar_n':int(len(similar)),'similar_summary':similar_summary.replace({np.nan:None}).to_dict('records'),
         'current':{'report_date':str(current.report_date.date()),'oi':float(current.oi),'asset_net':float(current.asset_net),'lev_net':float(current.lev_net),'dealer_net':float(current.dealer_net),'asset_net_pct_oi':float(current.asset_net_pct_oi),'lev_net_pct_oi':float(current.lev_net_pct_oi),'dealer_net_pct_oi':float(current.dealer_net_pct_oi),'lev_pctile_full':float(current.lev_pctile_full)}}
print('\nRESULT_JSON='+json.dumps(payload,separators=(',',':')))
