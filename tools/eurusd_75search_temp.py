import runpy, itertools, math, json
import numpy as np
import pandas as pd

ns=runpy.run_path('tools/cot_eurusd_backtest_refine_temp.py')
df=ns['df'].copy(); preds=ns['preds']; rules=ns['rules']

# Additional short horizons.
for h in [2,3]:
    df[f'fret{h}']=np.log(df.eurusd.shift(-h)/df.eurusd)
    df[f'y{h}']=(df[f'fret{h}']>0).astype(float)
    df.loc[df[f'fret{h}'].isna(),f'y{h}']=np.nan

def wilson(k,n,z=1.959963984540054):
    if n<=0:return (np.nan,np.nan)
    p=k/n; den=1+z*z/n; ctr=(p+z*z/(2*n))/den
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return ctr-half,ctr+half

def spaced(sub, min_days=1):
    if len(sub)==0:return sub
    sub=sub.sort_values('date')
    keep=[]; last=None
    for i,r in sub.iterrows():
        d=pd.Timestamp(r.date)
        if last is None or (d-last).days>=min_days:
            keep.append(i); last=d
    return sub.loc[keep]

print('\n=== EXTENDED CONFIDENCE / AGREEMENT SEARCH ===')
rows=[]
for h,pr0 in preds.items():
    pr=pr0.copy(); pr['date']=pd.to_datetime(pr.date)
    for t in [.60,.625,.65,.675,.70,.725,.75,.775,.80]:
        # ensemble
        use=(pr.p>=t)|(pr.p<=1-t); q=pr[use].copy(); pred=(q.p>=.5).astype(int)
        if len(q):
            acc=float((pred==q.y).mean()); lo,hi=wilson(int((pred==q.y).sum()),len(q))
            rows.append(['ensemble',h,t,len(q),len(q)/len(pr),acc,lo,hi])
        # both component models independently strong in same direction
        long=(pr.p_logit>=t)&(pr.p_hgb>=t); short=(pr.p_logit<=1-t)&(pr.p_hgb<=1-t)
        q=pr[long|short].copy(); pred=np.where(long[long|short],1,0)
        if len(q):
            acc=float((pred==q.y.to_numpy()).mean()); lo,hi=wilson(int((pred==q.y.to_numpy()).sum()),len(q))
            rows.append(['dual_strong',h,t,len(q),len(q)/len(pr),acc,lo,hi])
cr=pd.DataFrame(rows,columns=['method','h','threshold','n','coverage','accuracy','wilson_lo','wilson_hi'])
print(cr.assign(coverage=lambda x:(100*x.coverage).round(2),accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),wilson_hi=lambda x:(100*x.wilson_hi).round(2)).to_string(index=False))

# Rule mining: thresholds are recomputed from ONLY past data for each next-year test.
# Features chosen for interpretability and availability.
FEATURES=['ret1','ret5','ret20','ma50_gap','vol20','dgs2_chg1','dgs2_chg5','dgs2_chg20',
          'policy_spread_chg20','usd_ret5','usd_ret20','brent_ret5','brent_ret20','vix_chg5',
          'asset_net_pct_oi','lev_net_pct_oi','dealer_net_pct_oi','lev_chg4']

# Build condition matrices for a training set from its own quantiles, then apply same numeric cutoffs to test.
def conditions_from_train(train,test,qtail=.20):
    trc={}; tec={}; defs=[]
    for f in FEATURES:
        s=pd.to_numeric(train[f],errors='coerce').dropna()
        if len(s)<200: continue
        lo=float(s.quantile(qtail)); hi=float(s.quantile(1-qtail))
        for tag,thr,op in [('lo',lo,'le'),('hi',hi,'ge')]:
            name=f'{f}_{tag}'
            if op=='le': trc[name]=(train[f]<=thr).fillna(False).to_numpy(); tec[name]=(test[f]<=thr).fillna(False).to_numpy()
            else: trc[name]=(train[f]>=thr).fillna(False).to_numpy(); tec[name]=(test[f]>=thr).fillna(False).to_numpy()
            defs.append((name,f,op,thr))
    return trc,tec,defs

def mine_policy(h,combo_size=3,qtail=.20,min_train=60,topn=5,consensus=False):
    oos=[]; chosen=[]
    target=f'y{h}'
    for year in range(2016,2027):
        train=df[(df.date<pd.Timestamp(f'{year}-01-01')) & df[target].notna() & (df.date>=pd.Timestamp('2008-01-01'))].copy()
        test=df[(df.date>=pd.Timestamp(f'{year}-01-01')) & (df.date<pd.Timestamp(f'{year+1}-01-01')) & df[target].notna()].copy()
        if len(train)<1200 or len(test)==0: continue
        trc,tec,defs=conditions_from_train(train,test,qtail=qtail)
        names=list(trc)
        yt=train[target].astype(int).to_numpy()
        candidates=[]
        # Prevent logically redundant same-feature pairs in a conjunction.
        fmap={d[0]:d[1] for d in defs}
        for combo in itertools.combinations(names,combo_size):
            if len({fmap[c] for c in combo})<combo_size: continue
            m=np.ones(len(train),dtype=bool)
            for c in combo:m &= trc[c]
            n=int(m.sum())
            if n<min_train: continue
            up=float(yt[m].mean()); direction=1 if up>=.5 else 0
            k=int((yt[m]==direction).sum()); acc=k/n; lo,_=wilson(k,n)
            # Favor actual estimated edge but penalize tiny samples via Wilson lower bound.
            candidates.append((lo,acc,n,direction,combo))
        if not candidates: continue
        candidates.sort(reverse=True,key=lambda z:(z[0],z[1],z[2]))
        selected=candidates[:topn]
        chosen.append((year,selected[0]))
        votes=np.zeros(len(test),dtype=int); active=np.zeros(len(test),dtype=int)
        for _,_,_,direction,combo in selected:
            m=np.ones(len(test),dtype=bool)
            for c in combo:m &= tec[c]
            votes[m] += (1 if direction==1 else -1)
            active[m] += 1
        if consensus:
            sig=(active>=2)&(np.abs(votes)==active)  # at least 2 active rules, unanimous
        else:
            sig=active>=1
        pred=np.where(votes>=0,1,0)
        q=test.loc[sig,['date',target,f'fret{h}']].copy()
        q['pred']=pred[sig]; q['year']=year; q['active']=active[sig]
        oos.append(q)
    if not oos:return None,None
    oo=pd.concat(oos,ignore_index=True).sort_values('date')
    # Reduce serial overlap. For h-day horizons, require at least h calendar days between signals.
    oo2=spaced(oo,max(1,h))
    for label,q in [('raw',oo),('spaced',oo2),('recent2022+',oo2[oo2.date>=pd.Timestamp('2022-01-01')])]:
        if len(q):
            k=int((q['pred']==q[target].astype(int)).sum()); n=len(q); acc=k/n; lo,hi=wilson(k,n)
            yield label,n,acc,lo,hi,float((np.where(q.pred==1,1,-1)*q[f'fret{h}']).mean()),chosen

print('\n=== NESTED WALK-FORWARD RULE MINING ===')
mr=[]
for h in [1,2,3,5]:
  for qtail in [.10,.20,.30]:
    for size,minn in [(2,80),(3,50),(4,35)]:
      for consensus in [False,True]:
        res=mine_policy(h,size,qtail,minn,topn=5,consensus=consensus)
        if res is None: continue
        try:
          for label,n,acc,lo,hi,meanret,chosen in res:
            mr.append({'h':h,'qtail':qtail,'size':size,'consensus':consensus,'sample':label,'n':n,'accuracy':acc,'wilson_lo':lo,'wilson_hi':hi,'mean_signed_ret':meanret})
        except TypeError: pass
mrt=pd.DataFrame(mr)
if len(mrt):
    print(mrt.sort_values(['accuracy','n'],ascending=[False,False]).head(80).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),wilson_hi=lambda x:(100*x.wilson_hi).round(2),mean_signed_ret=lambda x:(100*x.mean_signed_ret).round(3)).to_string(index=False))

# Pre-specified interpretable interaction rules, no mining on outcomes.
print('\n=== PRE-SPECIFIED EXTREME INTERACTIONS ===')
# Rolling thresholds use only prior observations.
for f in ['ret1','ret5','dgs2_chg1','dgs2_chg5','usd_ret5','brent_ret20','vix_chg5','lev_net_pct_oi']:
    for q in [.1,.2,.8,.9]:
        df[f'{f}_q{int(q*100)}']=df[f].rolling(756,min_periods=252).quantile(q).shift(1)
interactions={
    'EUR_up_extreme_rates_down': (df.ret1>=df.ret1_q90)&(df.dgs2_chg1<=df.dgs2_chg1_q20),
    'EUR_up_extreme_USD_down': (df.ret1>=df.ret1_q90)&(df.usd_ret5<=df.usd_ret5_q20),
    'EUR_up_extreme_oil_up': (df.ret1>=df.ret1_q90)&(df.brent_ret20>=df.brent_ret20_q80),
    'trend_up_rates_down_usd_down': (df.ret20>0)&(df.dgs2_chg5<=df.dgs2_chg5_q20)&(df.usd_ret5<=df.usd_ret5_q20),
    'trend_up_rates_down_oil_up': (df.ret20>0)&(df.dgs2_chg5<=df.dgs2_chg5_q20)&(df.brent_ret20>=df.brent_ret20_q80),
    'trend_up_lev_extreme_short': (df.ret20>0)&(df.lev_net_pct_oi<=df.lev_net_pct_oi_q20),
    'trend_down_lev_extreme_short': (df.ret20<0)&(df.lev_net_pct_oi<=df.lev_net_pct_oi_q20),
}
ir=[]
for name,mask in interactions.items():
  idx=np.flatnonzero(mask.fillna(False).to_numpy()); keep=[]; last=-99
  for i in idx:
    if i-last>=5: keep.append(i); last=i
  sub=df.iloc[keep]
  for h in [1,2,3,5]:
    s=sub[f'fret{h}'].dropna()
    if len(s)<10:continue
    up=float((s>0).mean()); direction='UP' if up>=.5 else 'DOWN'; acc=max(up,1-up); k=int(round(acc*len(s))); lo,hi=wilson(k,len(s))
    ir.append({'rule':name,'h':h,'n':len(s),'direction':direction,'accuracy':acc,'wilson_lo':lo,'median_ret':float(s.median())})
irt=pd.DataFrame(ir)
print(irt.sort_values(['accuracy','n'],ascending=[False,False]).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),median_ret=lambda x:(100*x.median_ret).round(3)).to_string(index=False))

# Summarize candidates meeting 75% observed accuracy with sane sample size.
print('\n=== 75PCT CANDIDATES ===')
cands=[]
if len(cr):
    for _,r in cr[(cr.accuracy>=.75)&(cr.n>=30)].iterrows():cands.append({'source':'model_conf','desc':f"{r.method} h{int(r.h)} t{r.threshold}",'n':int(r.n),'accuracy':r.accuracy,'wilson_lo':r.wilson_lo})
if len(mrt):
    for _,r in mrt[(mrt.accuracy>=.75)&(mrt.n>=30)&(mrt['sample'].isin(['spaced','recent2022+']))].iterrows():cands.append({'source':'rule_mining','desc':f"h{int(r.h)} q{r.qtail} size{int(r['size'])} consensus{bool(r.consensus)} {r['sample']}",'n':int(r.n),'accuracy':r.accuracy,'wilson_lo':r.wilson_lo})
if len(irt):
    for _,r in irt[(irt.accuracy>=.75)&(irt.n>=30)].iterrows():cands.append({'source':'interaction','desc':f"{r['rule']} h{int(r.h)} {r.direction}",'n':int(r.n),'accuracy':r.accuracy,'wilson_lo':r.wilson_lo})
if cands:
    print(pd.DataFrame(cands).sort_values(['wilson_lo','n'],ascending=False).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2)).to_string(index=False))
else:
    print('NONE_WITH_N>=30')
