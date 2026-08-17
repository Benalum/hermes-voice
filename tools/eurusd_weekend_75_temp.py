import runpy, math, itertools
import numpy as np
import pandas as pd

ns=runpy.run_path('tools/cot_eurusd_backtest_refine_temp.py')
df=ns['df'].copy().sort_values('date').reset_index(drop=True)
# Friday close -> next available FX observation (normally Monday), and next 2/3 observations.
df['weekday']=df.date.dt.weekday
for h in [1,2,3]:
    df[f'fret{h}']=np.log(df.eurusd.shift(-h)/df.eurusd)
    df[f'y{h}']=(df[f'fret{h}']>0).astype(float); df.loc[df[f'fret{h}'].isna(),f'y{h}']=np.nan

# Weekend-specific context.
df['week_ret']=np.log(df.eurusd/df.eurusd.shift(5))
df['month_ret']=np.log(df.eurusd/df.eurusd.shift(20))
df['near60high']=df.eurusd>=.995*df.eurusd.rolling(60).max().shift(1)
df['near60low']=df.eurusd<=1.005*df.eurusd.rolling(60).min().shift(1)
df['fri_up']=(df.ret1>0); df['fri_dn']=(df.ret1<0)
df['week_up']=df.week_ret>0; df['week_dn']=df.week_ret<0

# Rolling quantiles based only on past 3 years.
F=['ret1','week_ret','ret20','dgs2_chg1','dgs2_chg5','usd_ret5','brent_ret20','vix_chg5','lev_net_pct_oi','asset_net_pct_oi']
for f in F:
  for q in [.10,.20,.30,.70,.80,.90]:
    df[f'{f}_q{int(q*100)}']=df[f].rolling(756,min_periods=252).quantile(q).shift(1)

def lo(f,q=20): return df[f]<=df[f'{f}_q{q}']
def hi(f,q=80): return df[f]>=df[f'{f}_q{q}']

def wilson(k,n,z=1.959963984540054):
    if n<=0:return np.nan,np.nan
    p=k/n; den=1+z*z/n; ctr=(p+z*z/(2*n))/den; half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return ctr-half,ctr+half

fr=df[df.weekday==4].copy()
# Hand hypotheses.
patterns={
 'fri_up': fr.fri_up,
 'fri_dn': fr.fri_dn,
 'week_up': fr.week_up,
 'week_dn': fr.week_dn,
 'fri_ext_up': hi('ret1',80).reindex(fr.index),
 'fri_ext_dn': lo('ret1',20).reindex(fr.index),
 'week_ext_up': hi('week_ret',80).reindex(fr.index),
 'week_ext_dn': lo('week_ret',20).reindex(fr.index),
 'near_high': fr.near60high,
 'near_low': fr.near60low,
 'near_high_week_up': fr.near60high & fr.week_up,
 'near_low_week_dn': fr.near60low & fr.week_dn,
 'rates_fall': lo('dgs2_chg5',20).reindex(fr.index),
 'rates_rise': hi('dgs2_chg5',80).reindex(fr.index),
 'usd_fall': lo('usd_ret5',20).reindex(fr.index),
 'usd_rise': hi('usd_ret5',80).reindex(fr.index),
 'oil_surge': hi('brent_ret20',80).reindex(fr.index),
 'near_high_rates_fall': fr.near60high & lo('dgs2_chg5',20).reindex(fr.index),
 'near_high_rates_fall_oil': fr.near60high & lo('dgs2_chg5',20).reindex(fr.index) & hi('brent_ret20',80).reindex(fr.index),
 'week_up_rates_fall': fr.week_up & lo('dgs2_chg5',20).reindex(fr.index),
 'week_up_usd_fall': fr.week_up & lo('usd_ret5',20).reindex(fr.index),
 'week_up_rates_usd_fall': fr.week_up & lo('dgs2_chg5',20).reindex(fr.index)&lo('usd_ret5',20).reindex(fr.index),
 'week_up_oil_surge': fr.week_up & hi('brent_ret20',80).reindex(fr.index),
 'asset_long_lev_short': (fr.asset_net_pct_oi>0)&(fr.lev_net_pct_oi<0),
 'week_up_asset_long_lev_short': fr.week_up&(fr.asset_net_pct_oi>0)&(fr.lev_net_pct_oi<0),
}
print('=== WEEKEND HAND PATTERNS ===')
rows=[]
for name,mask in patterns.items():
  sub=fr.loc[mask.fillna(False)]
  for h in [1,2,3]:
    s=sub[f'fret{h}'].dropna(); n=len(s)
    if n<8:continue
    up=float((s>0).mean()); direction='UP' if up>=.5 else 'DOWN'; k=int((s>0).sum()) if direction=='UP' else int((s<0).sum()); acc=k/n; L,U=wilson(k,n)
    rows.append(dict(pattern=name,h=h,n=n,direction=direction,accuracy=acc,wilson_lo=L,median=float(s.median())))
r=pd.DataFrame(rows)
print(r.sort_values(['accuracy','n'],ascending=[False,False]).head(80).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),median=lambda x:(100*x['median']).round(3)).to_string(index=False))

# Candidate Friday features, binary state with nested annual learning.
BITS={
 'fri_up':fr.fri_up,
 'week_up':fr.week_up,
 'near_high':fr.near60high,
 'rates_down':fr.dgs2_chg5<0,
 'usd_down':fr.usd_ret5<0,
 'oil_up':fr.brent_ret20>0,
 'vix_down':fr.vix_chg5<0,
 'asset_long':fr.asset_net_pct_oi>0,
 'lev_short':fr.lev_net_pct_oi<0,
}
state=np.zeros(len(fr),np.int64)
for j,b in enumerate(BITS.values()):state+=b.fillna(False).to_numpy(np.int64)*(1<<j)
fr['state9']=state
print('\n=== NESTED FRIDAY STATE MODEL ===')
rr=[]
for h in [1,2,3]:
  target=f'y{h}'
  for min_train in [8,12,20,30]:
    for amin in [.60,.65,.70,.75,.80]:
      out=[]
      for year in range(2016,2027):
        tr=fr[(fr.date<pd.Timestamp(f'{year}-01-01'))&(fr.date>=pd.Timestamp('2008-01-01'))&fr[target].notna()]
        te=fr[(fr.date>=pd.Timestamp(f'{year}-01-01'))&(fr.date<pd.Timestamp(f'{year+1}-01-01'))&fr[target].notna()]
        grp=tr.groupby('state9')[target].agg(['count','mean']);pol={}
        for st,z in grp.iterrows():
          n=int(z['count']); up=float(z['mean']); acc=max(up,1-up)
          if n>=min_train and acc>=amin:pol[int(st)]=1 if up>=.5 else 0
        q=te[te.state9.isin(pol)].copy()
        if len(q):q['pred']=q.state9.map(pol).astype(int);out.append(q[['date',target,'pred']])
      if not out:continue
      oo=pd.concat(out); k=int((oo.pred==oo[target].astype(int)).sum());n=len(oo);L,U=wilson(k,n)
      recent=oo[oo.date>=pd.Timestamp('2022-01-01')]; kr=int((recent.pred==recent[target].astype(int)).sum()) if len(recent) else 0; LR,UR=wilson(kr,len(recent)) if len(recent) else (np.nan,np.nan)
      rr.append(dict(h=h,min_train=min_train,amin=amin,n=n,accuracy=k/n,wilson_lo=L,recent_n=len(recent),recent_acc=kr/len(recent) if len(recent) else np.nan,recent_lo=LR))
st=pd.DataFrame(rr)
print(st.sort_values(['accuracy','n'],ascending=[False,False]).head(80).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),recent_acc=lambda x:(100*x.recent_acc).round(2),recent_lo=lambda x:(100*x.recent_lo).round(2)).to_string(index=False))

# Nested conjunction miner on Friday only, selecting rules from prior years then applying next year.
# Conditions use rolling/past thresholds already encoded, so no future threshold leakage.
conds={
 'fri_up':fr.fri_up,'fri_dn':fr.fri_dn,'week_up':fr.week_up,'week_dn':fr.week_dn,
 'near_high':fr.near60high,'near_low':fr.near60low,
 'rates_lo':lo('dgs2_chg5',20).reindex(fr.index),'rates_hi':hi('dgs2_chg5',80).reindex(fr.index),
 'usd_lo':lo('usd_ret5',20).reindex(fr.index),'usd_hi':hi('usd_ret5',80).reindex(fr.index),
 'oil_hi':hi('brent_ret20',80).reindex(fr.index),'oil_lo':lo('brent_ret20',20).reindex(fr.index),
 'vix_hi':hi('vix_chg5',80).reindex(fr.index),'vix_lo':lo('vix_chg5',20).reindex(fr.index),
 'lev_short':fr.lev_net_pct_oi<0,'lev_long':fr.lev_net_pct_oi>=0,
 'asset_long':fr.asset_net_pct_oi>0,'asset_short':fr.asset_net_pct_oi<=0,
}
# avoid contradictory pairs by base group.
groups={c:c.split('_')[0] for c in conds}; groups.update({'near_high':'near','near_low':'near','fri_up':'fri','fri_dn':'fri','week_up':'week','week_dn':'week','lev_short':'lev','lev_long':'lev','asset_long':'asset','asset_short':'asset'})
print('\n=== NESTED FRIDAY CONJUNCTIONS ===')
res=[]
for h in [1,2,3]:
 target=f'y{h}'
 for size in [2,3,4]:
  out=[]
  for year in range(2016,2027):
   trmask=(fr.date<pd.Timestamp(f'{year}-01-01'))&(fr.date>=pd.Timestamp('2008-01-01'))&fr[target].notna()
   temask=(fr.date>=pd.Timestamp(f'{year}-01-01'))&(fr.date<pd.Timestamp(f'{year+1}-01-01'))&fr[target].notna()
   cand=[]
   for combo in itertools.combinations(conds.keys(),size):
    if len({groups[c] for c in combo})<size:continue
    m=trmask.copy()
    for c in combo:m &= conds[c].fillna(False)
    n=int(m.sum())
    if n<20:continue
    y=fr.loc[m,target].astype(int);up=float(y.mean());d=1 if up>=.5 else 0;k=int((y==d).sum());acc=k/n;L,_=wilson(k,n)
    cand.append((L,acc,n,d,combo))
   if not cand:continue
   chosen=sorted(cand,reverse=True)[:3]
   te=fr.loc[temask].copy();votes=np.zeros(len(te),int);act=np.zeros(len(te),int)
   for _,_,_,d,combo in chosen:
    m=np.ones(len(te),bool)
    for c in combo:m &= conds[c].reindex(te.index).fillna(False).to_numpy()
    votes[m]+=1 if d else -1;act[m]+=1
   use=(act>=1)
   q=te.loc[use,['date',target]].copy();q['pred']=(votes[use]>=0).astype(int)
   if len(q):out.append(q)
  if out:
   oo=pd.concat(out);k=int((oo.pred==oo[target].astype(int)).sum());n=len(oo);L,U=wilson(k,n);recent=oo[oo.date>=pd.Timestamp('2022-01-01')];kr=int((recent.pred==recent[target].astype(int)).sum()) if len(recent) else 0;LR,UR=wilson(kr,len(recent)) if len(recent) else (np.nan,np.nan)
   res.append(dict(h=h,size=size,n=n,accuracy=k/n,wilson_lo=L,recent_n=len(recent),recent_acc=kr/len(recent) if len(recent) else np.nan,recent_lo=LR))
co=pd.DataFrame(res)
print(co.assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),recent_acc=lambda x:(100*x.recent_acc).round(2),recent_lo=lambda x:(100*x.recent_lo).round(2)).to_string(index=False))

print('\n=== WEEKEND 75 N>=30 CHECK ===')
print('hand',len(r[(r.accuracy>=.75)&(r.n>=30)]),'state',len(st[(st.accuracy>=.75)&(st.n>=30)]),'conj',len(co[(co.accuracy>=.75)&(co.n>=30)]))
