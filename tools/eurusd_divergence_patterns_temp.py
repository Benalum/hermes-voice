import runpy, math, itertools
import numpy as np
import pandas as pd

ns=runpy.run_path('tools/cot_eurusd_backtest_refine_temp.py')
df=ns['df'].copy()
for h in [2,3]:
    df[f'fret{h}']=np.log(df.eurusd.shift(-h)/df.eurusd)
    df[f'y{h}']=(df[f'fret{h}']>0).astype(float); df.loc[df[f'fret{h}'].isna(),f'y{h}']=np.nan
# Extra same-day features.
df['usd_ret1']=np.log(df.dtwexbgs).diff(1)
df['oil_ret1']=np.log(df.dcoilbrenteu).diff(1)
df['streak_up3']=(df.ret1>0)&(df.ret1.shift(1)>0)&(df.ret1.shift(2)>0)
df['streak_dn3']=(df.ret1<0)&(df.ret1.shift(1)<0)&(df.ret1.shift(2)<0)
df['streak_up4']=df.streak_up3&(df.ret1.shift(3)>0)
df['streak_dn4']=df.streak_dn3&(df.ret1.shift(3)<0)
roll_hi=df.eurusd.rolling(60).max().shift(1); roll_lo=df.eurusd.rolling(60).min().shift(1)
df['near_high']=df.eurusd>=.995*roll_hi; df['near_low']=df.eurusd<=1.005*roll_lo

# Rolling quantiles use only prior information.
F=['ret1','ret5','dgs2_chg1','dgs2_chg5','usd_ret1','usd_ret5','brent_ret20','oil_ret1','vix_chg5']
for f in F:
    for q in [.10,.15,.20,.80,.85,.90]:
        df[f'{f}_q{int(q*100)}']=df[f].rolling(756,min_periods=252).quantile(q).shift(1)

def low(f,q=20):return df[f]<=df[f'{f}_q{q}']
def high(f,q=80):return df[f]>=df[f'{f}_q{q}']

def wilson(k,n,z=1.959963984540054):
    if n<=0:return np.nan,np.nan
    p=k/n; den=1+z*z/n; ctr=(p+z*z/(2*n))/den; half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return ctr-half,ctr+half

def space(mask,gap=5):
    idx=np.flatnonzero(mask.fillna(False).to_numpy()); keep=[]; last=-999
    for i in idx:
        if i-last>=gap:keep.append(i);last=i
    return df.iloc[keep]

patterns={}
# Catch-up / failure-to-confirm patterns.
patterns['rates_bull_EUR_down']=low('dgs2_chg1',20)&(df.ret1<0)
patterns['rates_bear_EUR_up']=high('dgs2_chg1',80)&(df.ret1>0)
patterns['usd_bull_EUR_down']=low('usd_ret1',20)&(df.ret1<0)
patterns['usd_bear_EUR_up']=high('usd_ret1',80)&(df.ret1>0)
patterns['ratesUSD_bull_EUR_down']=low('dgs2_chg1',20)&low('usd_ret1',20)&(df.ret1<0)
patterns['ratesUSD_bear_EUR_up']=high('dgs2_chg1',80)&high('usd_ret1',80)&(df.ret1>0)
# Overreaction with/without confirmation.
patterns['EUR_ext_up_rates_bull']=high('ret1',85)&low('dgs2_chg1',20)
patterns['EUR_ext_up_rates_notbull']=high('ret1',85)&~low('dgs2_chg1',20)
patterns['EUR_ext_dn_rates_bear']=low('ret1',15)&high('dgs2_chg1',80)
patterns['EUR_ext_dn_rates_notbear']=low('ret1',15)&~high('dgs2_chg1',80)
patterns['EUR_ext_up_USD_bull']=high('ret1',85)&low('usd_ret1',20)
patterns['EUR_ext_up_USD_notbull']=high('ret1',85)&~low('usd_ret1',20)
patterns['EUR_ext_dn_USD_bear']=low('ret1',15)&high('usd_ret1',80)
patterns['EUR_ext_dn_USD_notbear']=low('ret1',15)&~high('usd_ret1',80)
# Strong combined confirmation or disagreement.
patterns['EUR_up_confirm_both']=high('ret1',80)&low('dgs2_chg1',20)&low('usd_ret1',20)
patterns['EUR_dn_confirm_both']=low('ret1',20)&high('dgs2_chg1',80)&high('usd_ret1',80)
patterns['EUR_up_against_both']=high('ret1',80)&high('dgs2_chg1',80)&high('usd_ret1',80)
patterns['EUR_dn_against_both']=low('ret1',20)&low('dgs2_chg1',20)&low('usd_ret1',20)
# Streaks and location.
patterns['up3_near_high']=df.streak_up3&df.near_high
patterns['dn3_near_low']=df.streak_dn3&df.near_low
patterns['up4']=df.streak_up4
patterns['dn4']=df.streak_dn4
patterns['up3_rates_falling']=df.streak_up3&low('dgs2_chg5',20)
patterns['dn3_rates_rising']=df.streak_dn3&high('dgs2_chg5',80)
patterns['near_high_rates_falling']=df.near_high&low('dgs2_chg5',20)
patterns['near_low_rates_rising']=df.near_low&high('dgs2_chg5',80)
# Oil interaction.
patterns['near_high_oil_surge']=df.near_high&high('brent_ret20',85)
patterns['EUR_up_oil_surge']=high('ret1',80)&high('brent_ret20',85)
patterns['EUR_dn_oil_surge']=low('ret1',20)&high('brent_ret20',85)
patterns['rates_fall_oil_surge']=low('dgs2_chg5',20)&high('brent_ret20',85)
# COT + divergence.
patterns['lev_short_rates_bull_EUR_down']=(df.lev_net_pct_oi<0)&low('dgs2_chg1',20)&(df.ret1<0)
patterns['asset_long_rates_bear_EUR_up']=(df.asset_net_pct_oi>0)&high('dgs2_chg1',80)&(df.ret1>0)

print('=== STATIC PATTERN RESULTS (5-day spacing) ===')
rows=[]
for name,mask in patterns.items():
    sub=space(mask,5)
    for h in [1,2,3,5]:
        s=sub[f'fret{h}'].dropna(); n=len(s)
        if n<8:continue
        up=float((s>0).mean()); acc=max(up,1-up); direction='UP' if up>=.5 else 'DOWN'; k=int((s>0).sum()) if direction=='UP' else int((s<0).sum()); lo,hi=wilson(k,n)
        rows.append(dict(pattern=name,h=h,n=n,direction=direction,accuracy=acc,wilson_lo=lo,wilson_hi=hi,median=float(s.median()),recent_n=int((sub[sub.date>=pd.Timestamp('2020-01-01')][f'fret{h}'].notna()).sum())))
r=pd.DataFrame(rows)
print(r.sort_values(['accuracy','n'],ascending=[False,False]).head(100).assign(accuracy=lambda x:(100*x.accuracy).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),median=lambda x:(100*x['median']).round(3)).to_string(index=False))

# Development/holdout: choose promising patterns using data through 2019, then evaluate 2020+ only.
print('\n=== LOCKED 2020+ HOLDOUT FOR PRE-2019 WINNERS ===')
hrows=[]
for h in [1,2,3,5]:
    candidates=[]
    for name,mask in patterns.items():
        sub=space(mask&(df.date<pd.Timestamp('2020-01-01')),5); s=sub[f'fret{h}'].dropna(); n=len(s)
        if n<20:continue
        up=float((s>0).mean()); direction=1 if up>=.5 else 0; acc=max(up,1-up); k=int((s>0).sum()) if direction else int((s<0).sum()); lo,_=wilson(k,n)
        candidates.append((lo,acc,n,direction,name))
    candidates=sorted(candidates,reverse=True)[:10]
    for lo_train,acc_train,n_train,direction,name in candidates:
        sub=space(patterns[name]&(df.date>=pd.Timestamp('2020-01-01')),5); s=sub[f'fret{h}'].dropna(); n=len(s)
        if not n:continue
        k=int((s>0).sum()) if direction else int((s<0).sum()); acc=k/n; lo,hi=wilson(k,n)
        hrows.append(dict(pattern=name,h=h,n_train=n_train,train_acc=acc_train,n_hold=n,dir='UP' if direction else 'DOWN',hold_acc=acc,wilson_lo=lo,median=float(s.median())))
hr=pd.DataFrame(hrows)
print(hr.sort_values(['hold_acc','n_hold'],ascending=[False,False]).assign(train_acc=lambda x:(100*x.train_acc).round(2),hold_acc=lambda x:(100*x.hold_acc).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),median=lambda x:(100*x['median']).round(3)).to_string(index=False))

# Nested annual: each year choose top 3 patterns based only on prior history; trade only when all active chosen patterns agree.
print('\n=== NESTED ANNUAL PATTERN ENSEMBLE ===')
ens=[]
for h in [1,2,3,5]:
    target=f'y{h}'; allq=[]
    for year in range(2016,2027):
        train_end=pd.Timestamp(f'{year}-01-01')
        cand=[]
        for name,mask in patterns.items():
            sub=space(mask&(df.date<train_end)&(df.date>=pd.Timestamp('2008-01-01')),5); s=sub[f'fret{h}'].dropna(); n=len(s)
            if n<20:continue
            up=float((s>0).mean()); direction=1 if up>=.5 else 0; k=int((s>0).sum()) if direction else int((s<0).sum()); acc=k/n; lo,_=wilson(k,n)
            cand.append((lo,acc,n,direction,name))
        chosen=sorted(cand,reverse=True)[:5]
        te=df[(df.date>=train_end)&(df.date<pd.Timestamp(f'{year+1}-01-01'))&df[target].notna()].copy()
        votes=np.zeros(len(te),int); active=np.zeros(len(te),int)
        for _,_,_,direction,name in chosen:
            m=patterns[name].reindex(te.index).fillna(False).to_numpy()
            votes[m]+=1 if direction else -1;active[m]+=1
        use=(active>=2)&(np.abs(votes)==active)
        if use.any():
            q=te.loc[use,['date',target]].copy();q['pred']=(votes[use]>0).astype(int);allq.append(q)
    if allq:
        q=pd.concat(allq).sort_values('date'); k=int((q.pred==q[target].astype(int)).sum()); n=len(q); lo,hi=wilson(k,n)
        qr=q[q.date>=pd.Timestamp('2022-01-01')]; kr=int((qr.pred==qr[target].astype(int)).sum()) if len(qr) else 0; lor,hir=wilson(kr,len(qr)) if len(qr) else (np.nan,np.nan)
        ens.append(dict(h=h,n=n,acc=k/n,wilson_lo=lo,recent_n=len(qr),recent_acc=kr/len(qr) if len(qr) else np.nan,recent_lo=lor))
e=pd.DataFrame(ens)
print(e.assign(acc=lambda x:(100*x.acc).round(2),wilson_lo=lambda x:(100*x.wilson_lo).round(2),recent_acc=lambda x:(100*x.recent_acc).round(2),recent_lo=lambda x:(100*x.recent_lo).round(2)).to_string(index=False))

print('\n=== 75% WITH N>=30 CHECK ===')
q1=r[(r.accuracy>=.75)&(r.n>=30)]
q2=hr[(hr.hold_acc>=.75)&(hr.n_hold>=30)]
q3=e[(e.acc>=.75)&(e.n>=30)]
print('static',len(q1),'holdout',len(q2),'nested',len(q3))
if len(q1):print(q1.to_string(index=False))
if len(q2):print(q2.to_string(index=False))
if len(q3):print(q3.to_string(index=False))
