import runpy, math, json
import numpy as np
import pandas as pd

ns=runpy.run_path('tools/cot_eurusd_backtest_refine_temp.py')
df=ns['df'].copy(); preds=ns['preds']
for h in [2,3]:
    df[f'fret{h}']=np.log(df.eurusd.shift(-h)/df.eurusd)
    df[f'y{h}']=(df[f'fret{h}']>0).astype(float)
    df.loc[df[f'fret{h}'].isna(),f'y{h}']=np.nan

def wilson(k,n,z=1.959963984540054):
    if n<=0:return np.nan,np.nan
    p=k/n; den=1+z*z/n; ctr=(p+z*z/(2*n))/den
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return ctr-half,ctr+half

def report(name,q,target,pred_col='pred'):
    if len(q)==0:return None
    y=q[target].astype(int).to_numpy(); p=q[pred_col].astype(int).to_numpy(); ok=(y==p)
    n=len(q); k=int(ok.sum()); lo,hi=wilson(k,n)
    return dict(name=name,n=n,accuracy=k/n,wilson_lo=lo,wilson_hi=hi)

print('\n=== VERY HIGH MODEL CONFIDENCE ===')
out=[]
for h,pr0 in preds.items():
    pr=pr0.copy(); pr['date']=pd.to_datetime(pr.date)
    for t in [.60,.625,.65,.675,.70,.725,.75,.775,.80,.825,.85,.875,.90]:
        # ensemble
        use=(pr.p>=t)|(pr.p<=1-t); q=pr[use].copy(); q['pred']=(q.p>=.5).astype(int)
        r=report(f'ensemble_h{h}_t{t}',q,'y');
        if r:r.update(h=h,t=t,method='ensemble',coverage=len(q)/len(pr)); out.append(r)
        # dual strong
        long=(pr.p_logit>=t)&(pr.p_hgb>=t); short=(pr.p_logit<=1-t)&(pr.p_hgb<=1-t)
        q=pr[long|short].copy(); q['pred']=np.where(long[long|short],1,0)
        r=report(f'dual_h{h}_t{t}',q,'y');
        if r:r.update(h=h,t=t,method='dual',coverage=len(q)/len(pr)); out.append(r)
res=pd.DataFrame(out)
print(res.assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),coverage=lambda x:(100*x.coverage).round(2)).to_string(index=False))

# -------- nested walk-forward binary state policies --------
# Eight interpretable pieces of information. State mapping is learned only on data before each test year.
state_bits={
 'trend_up': df.ret20>0,
 'above50': df.ma50_gap>0,
 'us2y_down': df.dgs2_chg5<0,
 'usd_down': df.usd_ret5<0,
 'oil_up': df.brent_ret20>0,
 'vix_down': df.vix_chg5<0,
 'asset_long': df.asset_net_pct_oi>0,
 'lev_short': df.lev_net_pct_oi<0,
}
state=np.zeros(len(df),dtype=np.int64)
for j,(k,b) in enumerate(state_bits.items()): state += b.fillna(False).to_numpy(dtype=np.int64)*(1<<j)
df['state8']=state

print('\n=== NESTED WALK-FORWARD 8-BIT STATES ===')
rows=[]
for h in [1,2,3,5]:
  target=f'y{h}'
  for min_train in [25,40,60,100]:
    for train_acc_min in [.60,.65,.70,.75,.80]:
      oos=[]
      for year in range(2016,2027):
        tr=df[(df.date<pd.Timestamp(f'{year}-01-01'))&(df.date>=pd.Timestamp('2008-01-01'))&df[target].notna()].copy()
        te=df[(df.date>=pd.Timestamp(f'{year}-01-01'))&(df.date<pd.Timestamp(f'{year+1}-01-01'))&df[target].notna()].copy()
        if len(tr)<1000 or len(te)==0:continue
        grp=tr.groupby('state8')[target].agg(['count','mean'])
        policy={}
        for st,r in grp.iterrows():
            n=int(r['count']); up=float(r['mean']); acc=max(up,1-up)
            if n>=min_train and acc>=train_acc_min:
                policy[int(st)]=1 if up>=.5 else 0
        if not policy:continue
        q=te[te.state8.isin(policy)].copy()
        if len(q):
            q['pred']=q.state8.map(policy).astype(int); q['year']=year; oos.append(q[['date',target,'pred']])
      if not oos:continue
      oo=pd.concat(oos,ignore_index=True).sort_values('date')
      for label,q in [('all',oo),('recent2022+',oo[oo.date>=pd.Timestamp('2022-01-01')])]:
        r=report('',q,target)
        if r:rows.append(dict(h=h,min_train=min_train,train_acc_min=train_acc_min,sample=label,**{k:r[k] for k in ['n','accuracy','wilson_lo','wilson_hi']}))
st=pd.DataFrame(rows)
print(st.sort_values(['accuracy','n'],ascending=[False,False]).head(80).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2)).to_string(index=False))

# -------- extreme shock states, rolling quantiles computed from prior 3y only --------
# Ternary categories for event-like moves: -1 extreme low, 0 normal, +1 extreme high.
for f in ['ret1','ret5','dgs2_chg1','dgs2_chg5','usd_ret5','brent_ret20','vix_chg5']:
    lo=df[f].rolling(756,min_periods=252).quantile(.15).shift(1)
    hi=df[f].rolling(756,min_periods=252).quantile(.85).shift(1)
    df[f'{f}_cat']=np.where(df[f]<=lo,-1,np.where(df[f]>=hi,1,0))
shock_cols=[f'{f}_cat' for f in ['ret1','ret5','dgs2_chg1','dgs2_chg5','usd_ret5','brent_ret20','vix_chg5']]
# encode base-3 state, plus COT signs
code=np.zeros(len(df),dtype=np.int64); mult=1
for c in shock_cols:
    code += (df[c].astype(int).to_numpy()+1)*mult; mult*=3
code += (df.asset_net_pct_oi.gt(0).fillna(False).to_numpy(dtype=np.int64))*mult; mult*=2
code += (df.lev_net_pct_oi.lt(0).fillna(False).to_numpy(dtype=np.int64))*mult
df['shock_state']=code

print('\n=== NESTED WALK-FORWARD EXTREME SHOCK STATES ===')
rows2=[]
for h in [1,2,3,5]:
  target=f'y{h}'
  for min_train in [12,20,30,40]:
    for train_acc_min in [.65,.70,.75,.80,.85]:
      oos=[]
      for year in range(2016,2027):
        tr=df[(df.date<pd.Timestamp(f'{year}-01-01'))&(df.date>=pd.Timestamp('2008-01-01'))&df[target].notna()].copy()
        te=df[(df.date>=pd.Timestamp(f'{year}-01-01'))&(df.date<pd.Timestamp(f'{year+1}-01-01'))&df[target].notna()].copy()
        grp=tr.groupby('shock_state')[target].agg(['count','mean']); policy={}
        for stt,r in grp.iterrows():
            n=int(r['count']); up=float(r['mean']); acc=max(up,1-up)
            if n>=min_train and acc>=train_acc_min:policy[int(stt)]=1 if up>=.5 else 0
        q=te[te.shock_state.isin(policy)].copy()
        if len(q):q['pred']=q.shock_state.map(policy).astype(int);oos.append(q[['date',target,'pred']])
      if not oos:continue
      oo=pd.concat(oos,ignore_index=True).sort_values('date')
      for label,q in [('all',oo),('recent2022+',oo[oo.date>=pd.Timestamp('2022-01-01')])]:
        r=report('',q,target)
        if r:rows2.append(dict(h=h,min_train=min_train,train_acc_min=train_acc_min,sample=label,**{k:r[k] for k in ['n','accuracy','wilson_lo','wilson_hi']}))
sh=pd.DataFrame(rows2)
print(sh.sort_values(['accuracy','n'],ascending=[False,False]).head(100).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2)).to_string(index=False))

print('\n=== ROBUST 75% CHECK ===')
c=[]
for src,tbl in [('model',res),('state8',st),('shock',sh)]:
    if len(tbl)==0:continue
    q=tbl[(tbl.accuracy>=.75)&(tbl.n>=30)]
    for _,r in q.iterrows():
        c.append({'source':src,'n':int(r.n),'accuracy':float(r.accuracy),'wilson_lo':float(r.wilson_lo),'details':str(r.to_dict())})
if c:
    cc=pd.DataFrame(c).sort_values(['wilson_lo','n'],ascending=False)
    print(cc.assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2)).to_string(index=False))
else:print('NONE_N>=30')
