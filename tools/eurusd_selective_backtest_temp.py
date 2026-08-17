import runpy, json
import numpy as np
import pandas as pd

ns=runpy.run_path('tools/cot_eurusd_backtest_refine_temp.py')
df=ns['df']; preds=ns['preds']; H=ns['HORIZONS']; latest=ns['latest']; latest_cot=ns['latest_cot']

print('\n=== SELECTIVE MODEL CONFIDENCE ===')
sel=[]
for h in H:
    pr=preds[h].copy()
    for edge in [.525,.55,.575,.60]:
        use=(pr.p>=edge)|(pr.p<=1-edge)
        q=pr[use]
        if len(q)==0: continue
        pred=(q.p>=.5).astype(int)
        acc=float((pred==q.y).mean())
        sel.append({'h':h,'threshold':edge,'n':len(q),'coverage':len(q)/len(pr),'accuracy':acc,'avg_conf':float(np.maximum(q.p,1-q.p).mean())})
print(pd.DataFrame(sel).assign(coverage=lambda x:(100*x.coverage).round(1),accuracy=lambda x:(100*x.accuracy).round(2),avg_conf=lambda x:(100*x.avg_conf).round(2)).to_string(index=False))

# Historical regimes analogous to current public conditions:
# A) EUR near a 60d high, U.S. 2y yield falling over 5d, AM long/leveraged short.
# B) same + oil up >=5% over 20 trading days.
# C) same + price above 50d MA.
df=df.copy()
df['near60high']=df.eurusd >= .995*df.eurusd.rolling(60).max()
df['rate_down']=df.dgs2_chg5<0
df['cot_diverge']=(df.asset_net_pct_oi>0)&(df.lev_net_pct_oi<0)
df['oil_up5']=df.brent_ret20>=np.log(1.05)
df['above50']=df.ma50_gap>0
regimes={
    'nearHigh_rateDown_COT': df.near60high & df.rate_down & df.cot_diverge,
    'plus_oilUp5': df.near60high & df.rate_down & df.cot_diverge & df.oil_up5,
    'plus_oilUp5_above50': df.near60high & df.rate_down & df.cot_diverge & df.oil_up5 & df.above50,
}
print('\n=== CURRENT-LIKE REGIME TESTS ===')
rows=[]
for name,mask in regimes.items():
    # one observation per 5 business days to reduce overlap/clustering
    idx=np.flatnonzero(mask.fillna(False).to_numpy())
    keep=[]; last=-99
    for i in idx:
        if i-last>=5: keep.append(i); last=i
    sub=df.iloc[keep]
    for h in H:
        s=sub[f'fret{h}'].dropna()
        rows.append({'regime':name,'h':h,'n':len(s),'up_rate':float((s>0).mean()) if len(s) else np.nan,
                     'mean':float(s.mean()) if len(s) else np.nan,'median':float(s.median()) if len(s) else np.nan,
                     'q25':float(s.quantile(.25)) if len(s) else np.nan,'q75':float(s.quantile(.75)) if len(s) else np.nan})
rt=pd.DataFrame(rows)
print(rt.assign(up_rate=lambda x:(100*x.up_rate).round(2),mean=lambda x:(100*x['mean']).round(3),median=lambda x:(100*x['median']).round(3),q25=lambda x:(100*x.q25).round(3),q75=lambda x:(100*x.q75).round(3)).to_string(index=False))

# What happened after failed vs successful recent-high tests? Use 5d future max/min as rough excursion.
df['fmax5']=pd.concat([np.log(df.eurusd.shift(-i)/df.eurusd) for i in range(1,6)],axis=1).max(axis=1)
df['fmin5']=pd.concat([np.log(df.eurusd.shift(-i)/df.eurusd) for i in range(1,6)],axis=1).min(axis=1)
sub=df[regimes['nearHigh_rateDown_COT'] & df.fret5.notna()].copy()
print('\nREGIME_5D_EXCURSION n',len(sub),'median_max_pct',round(100*sub.fmax5.median(),3),'median_min_pct',round(100*sub.fmin5.median(),3),
      'q75_max_pct',round(100*sub.fmax5.quantile(.75),3),'q25_min_pct',round(100*sub.fmin5.quantile(.25),3))
