import runpy
import numpy as np
import pandas as pd

ns = runpy.run_path('tools/cot_eurusd_backtest_temp.py')
bt=ns['bt']; cot=ns['cot']; current=ns['current']; summary=ns['summary']; pct=ns['pct']; px_on_after=ns['px_on_after']; H=ns['HORIZONS']

# Current percentile context: full 20y and recent 156 reports (~3y), both raw net and net/OI.
recent=cot[cot.report_date<=current.report_date].tail(156).copy()
def percentile_le(series, value):
    s=pd.to_numeric(series,errors='coerce').dropna()
    return float((s <= float(value)).mean())
print('\n=== CURRENT POSITIONING PERCENTILES ===')
print('full_history_lev_net_pct_oi_percentile', percentile_le(cot.lev_net_pct_oi,current.lev_net_pct_oi))
print('recent156_lev_net_raw_percentile', percentile_le(recent.lev_net,current.lev_net))
print('recent156_lev_net_pct_oi_percentile', percentile_le(recent.lev_net_pct_oi,current.lev_net_pct_oi))
print('recent156_asset_net_raw_percentile', percentile_le(recent.asset_net,current.asset_net))
print('recent156_asset_net_pct_oi_percentile', percentile_le(recent.asset_net_pct_oi,current.asset_net_pct_oi))

# Exact condition the user originally described: Asset Managers bullish + Leveraged Funds bearish + Dealers bearish.
triple=bt[(bt.asset_net>0)&(bt.lev_net<0)&(bt.dealer_net<0)].sort_values('report_date').copy()
triple['new_episode']=triple.report_date.diff().dt.days.fillna(999)>10
triple['episode_id']=triple.new_episode.cumsum().astype(int)
triple_eps=triple.groupby('episode_id',as_index=False).first()
print('\n=== TRIPLE CONDITION (ASSET+, LEV-, DEALER-) ===')
print('weeks',len(triple),'episodes',len(triple_eps))
print('TRIPLE_WEEKLY_PCT\n'+pct(summary(triple)).to_string(index=False))
print('TRIPLE_EPISODES_PCT\n'+pct(summary(triple_eps)).to_string(index=False))

# Add a prior-4-week bearish price trend, mimicking the present discussion rather than all regimes.
def trailing4(row):
    if pd.isna(row.entry_date) or not np.isfinite(row.entry_px): return np.nan
    _,p0=px_on_after(row.entry_date-pd.Timedelta(days=28),5)
    return row.entry_px/p0-1 if np.isfinite(p0) else np.nan
triple['prior4w_ret']=triple.apply(trailing4,axis=1)
triple_bear=triple[triple.prior4w_ret<0].copy()
triple_bear['new_bear_episode']=triple_bear.report_date.diff().dt.days.fillna(999)>10
triple_bear['bear_episode_id']=triple_bear.new_bear_episode.cumsum().astype(int)
triple_bear_eps=triple_bear.groupby('bear_episode_id',as_index=False).first()
print('\n=== TRIPLE CONDITION + EURUSD PRIOR 4W BEARISH ===')
print('weeks',len(triple_bear),'episodes',len(triple_bear_eps))
print('TRIPLE_BEAR_WEEKLY_PCT\n'+pct(summary(triple_bear)).to_string(index=False))
print('TRIPLE_BEAR_EPISODES_PCT\n'+pct(summary(triple_bear_eps)).to_string(index=False))

# Current-like independent analogues: compare current net/OI positioning only to starts of historical triple episodes.
cols=['asset_net_pct_oi','lev_net_pct_oi','dealer_net_pct_oi']
base=triple_eps[triple_eps.report_date < current.report_date-pd.Timedelta(days=180)].copy()
if len(base):
    base[cols]=base[cols].astype(float)
    # Normalize using all pre-current CFTC observations to avoid episode-only scale artifacts.
    hist=cot[cot.report_date<current.report_date-pd.Timedelta(days=180)].copy(); hist[cols]=hist[cols].astype(float)
    mu=hist[cols].mean().to_numpy(float); sd=hist[cols].std(ddof=0).to_numpy(float)
    cur=current[cols].astype(float).to_numpy(float)
    bz=(base[cols].to_numpy(float)-mu)/sd; cz=(cur-mu)/sd
    base['distance']=np.sqrt(np.square(bz-cz).sum(axis=1))
    ep_analog=base.nsmallest(min(10,len(base)),'distance').copy()
else:
    ep_analog=base
print('\n=== NEAREST INDEPENDENT TRIPLE-EPISODE ANALOGUES ===')
if len(ep_analog):
    print(ep_analog[['report_date','distance','asset_net','lev_net','dealer_net']+[f'ret_{h}w' for h in H]].to_string(index=False))
    print('EPISODE_ANALOG_SUMMARY_PCT\n'+pct(summary(ep_analog)).to_string(index=False))
else: print('none')

# Same, restricted to bearish-trend triple episode starts.
baseb=triple_bear_eps[triple_bear_eps.report_date < current.report_date-pd.Timedelta(days=180)].copy()
if len(baseb):
    baseb[cols]=baseb[cols].astype(float)
    hist=cot[cot.report_date<current.report_date-pd.Timedelta(days=180)].copy(); hist[cols]=hist[cols].astype(float)
    mu=hist[cols].mean().to_numpy(float); sd=hist[cols].std(ddof=0).to_numpy(float); cur=current[cols].astype(float).to_numpy(float)
    baseb['distance']=np.sqrt(np.square((baseb[cols].to_numpy(float)-mu)/sd-(cur-mu)/sd).sum(axis=1))
    epb_analog=baseb.nsmallest(min(10,len(baseb)),'distance').copy()
else: epb_analog=baseb
print('\n=== NEAREST INDEPENDENT BEAR-TREND TRIPLE ANALOGUES ===')
if len(epb_analog):
    print(epb_analog[['report_date','distance','prior4w_ret','asset_net','lev_net','dealer_net']+[f'ret_{h}w' for h in H]].to_string(index=False))
    print('BEAR_EPISODE_ANALOG_SUMMARY_PCT\n'+pct(summary(epb_analog)).to_string(index=False))
else: print('none')
