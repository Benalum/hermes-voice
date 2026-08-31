from __future__ import annotations

import argparse
import itertools
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

OHLCV = ["open", "high", "low", "close", "volume"]

@dataclass(frozen=True)
class Contract:
    symbol: str
    point_value: float
    tick_size: float = 0.10
    round_trip_fee: float = 2.38

@dataclass(frozen=True)
class Params:
    risk_reward: float = 1.5
    volume_multiple: float = 1.0
    pullback_atr: float = 0.45
    require_vwap: bool = True
    min_stop_points: float = 1.5
    max_stop_points: float = 8.0
    entry_buffer_ticks: int = 1
    stop_buffer_ticks: int = 1
    expiry_bars: int = 4
    max_trades_day: int = 3
    cooldown_minutes: int = 15

def load_csv(path):
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    df.index = pd.to_datetime(df.pop("datetime"), utc=True)
    for c in OHLCV:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[OHLCV].dropna(subset=["open","high","low","close"]).sort_index()

def resample(df, rule, tz=None, offset=None):
    x = df if tz is None else df.tz_convert(tz)
    kw = {"label":"right","closed":"right"}
    if offset: kw.update(origin="start_day", offset=offset)
    out = x.resample(rule, **kw).agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna(subset=["open","high","low","close"])
    if tz is not None: out = out.tz_convert("UTC")
    return out

def ema(s, n): return s.ewm(span=n, adjust=False, min_periods=n).mean()

def atr(df, n=14):
    pc = df.close.shift(1)
    tr = pd.concat([(df.high-df.low).abs(),(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean()

def rsi(s, n=14):
    d=s.diff(); g=d.clip(lower=0); l=-d.clip(upper=0)
    ag=g.ewm(alpha=1/n,adjust=False,min_periods=n).mean(); al=l.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    return (100-100/(1+ag/al.replace(0,np.nan))).fillna(50)

def session_vwap(df):
    local=df.index.tz_convert("America/New_York")
    day=pd.Series(local.date,index=df.index); hh=pd.Series(local.strftime("%H:%M"),index=df.index)
    active=(hh>="09:30")&(hh<="16:00")
    typ=(df.high+df.low+df.close)/3
    vol=df.volume.fillna(0).where(active,0.0); pv=(typ*df.volume.fillna(0)).where(active,0.0)
    return (pv.groupby(day).cumsum()/vol.groupby(day).cumsum().replace(0,np.nan)).where(active)

def merge_completed(base, tf, prefix):
    right=tf.rename(columns={c:f"{prefix}_{c}" for c in tf.columns}).sort_index()
    return pd.merge_asof(base.sort_index(),right,left_index=True,right_index=True,direction="backward",allow_exact_matches=True)

def build_base_features(base30):
    b=base30.copy().sort_index(); b["vwap"]=session_vwap(b)
    m1=resample(b,"1min"); m1["rsi"]=rsi(m1.close,14); m1["vol_med"]=m1.volume.rolling(20,min_periods=20).median(); m1["vol_ratio"]=m1.volume/m1.vol_med.replace(0,np.nan); m1["prior_high"]=m1.high.shift(1); m1["prior_low"]=m1.low.shift(1); m1["bull_break"]=(m1.close>m1.prior_high)&(m1.rsi>52); m1["bear_break"]=(m1.close<m1.prior_low)&(m1.rsi<48)
    m5=resample(b,"5min"); m5["ema"]=ema(m5.close,20); m5["atr"]=atr(m5,14); m5["swing_low"]=m5.low.rolling(4,min_periods=4).min(); m5["swing_high"]=m5.high.rolling(4,min_periods=4).max(); m5["long_distance_atr"]=(m5.low-m5.ema)/m5.atr.replace(0,np.nan); m5["short_distance_atr"]=(m5.ema-m5.high)/m5.atr.replace(0,np.nan); m5["above_ema"]=m5.close>=m5.ema; m5["below_ema"]=m5.close<=m5.ema
    m30=resample(b,"30min"); m30["ema"]=ema(m30.close,20); m30["ema_prev"]=m30.ema.shift(2); m30["bull"]=(m30.close>m30.ema)&(m30.ema>m30.ema_prev); m30["bear"]=(m30.close<m30.ema)&(m30.ema<m30.ema_prev)
    h4=resample(b,"4h",tz="America/New_York",offset="18h"); h4["ema_fast"]=ema(h4.close,20); h4["ema_slow"]=ema(h4.close,50); h4["bull"]=(h4.close>h4.ema_fast)&(h4.ema_fast>h4.ema_slow); h4["bear"]=(h4.close<h4.ema_fast)&(h4.ema_fast<h4.ema_slow)
    out=b.copy(); out=merge_completed(out,m1[["rsi","vol_ratio","bull_break","bear_break"]],"m1"); out=merge_completed(out,m5[["atr","swing_low","swing_high","long_distance_atr","short_distance_atr","above_ema","below_ema"]],"m5"); out=merge_completed(out,m30[["bull","bear"]],"m30"); out=merge_completed(out,h4[["bull","bear"]],"h4"); return out

def add_setups(f,p):
    x=f.copy(); bull_pull=(x.m5_long_distance_atr<=p.pullback_atr)&x.m5_above_ema.fillna(False); bear_pull=(x.m5_short_distance_atr<=p.pullback_atr)&x.m5_below_ema.fillna(False); bull_conf=x.m1_bull_break.fillna(False)&(x.m1_vol_ratio>=p.volume_multiple); bear_conf=x.m1_bear_break.fillna(False)&(x.m1_vol_ratio>=p.volume_multiple); vlong=(x.close>=x.vwap) if p.require_vwap else pd.Series(True,index=x.index); vshort=(x.close<=x.vwap) if p.require_vwap else pd.Series(True,index=x.index); x["long_setup"]=x.h4_bull.fillna(False)&x.m30_bull.fillna(False)&bull_pull&bull_conf&vlong; x["short_setup"]=x.h4_bear.fillna(False)&x.m30_bear.fillna(False)&bear_pull&bear_conf&vshort; return x

def run_engine(f,contract,p,slippage_ticks,trade_start,trade_end=None):
    trades=[]; pending=None; pos=None; cooldown=None; day_count={}; slip=slippage_ticks*contract.tick_size; idx=list(f.index)
    for i,ts in enumerate(idx):
        if ts<trade_start: continue
        if trade_end is not None and ts>trade_end: break
        row=f.loc[ts]; local=ts.tz_convert("America/New_York"); hh=local.strftime("%H:%M"); day=local.date(); day_count.setdefault(day,0)
        if pos is not None:
            side=pos["side"]; raw=None; reason=None
            if side=="long":
                if row.low<=pos["stop"]: raw,reason=min(pos["stop"],float(row.open)),"stop"
                elif row.high>=pos["target"]: raw,reason=pos["target"],"target"
            else:
                if row.high>=pos["stop"]: raw,reason=max(pos["stop"],float(row.open)),"stop"
                elif row.low<=pos["target"]: raw,reason=pos["target"],"target"
            if hh>="15:55" and raw is None: raw,reason=float(row.close),"session_flatten"
            if raw is not None:
                exit_fill=raw-slip if side=="long" else raw+slip; direction=1 if side=="long" else -1; gross=direction*(raw-pos["entry_raw"])*contract.point_value; net=direction*(exit_fill-pos["entry_fill"])*contract.point_value-contract.round_trip_fee
                trades.append({"side":side,"signal_time":pos["signal_time"],"entry_time":pos["entry_time"],"exit_time":ts,"entry_raw":pos["entry_raw"],"entry_fill":pos["entry_fill"],"stop":pos["stop"],"target":pos["target"],"exit_raw":raw,"exit_fill":exit_fill,"gross_pnl":gross,"net_pnl":net,"fees":contract.round_trip_fee,"slippage_ticks_each_side":slippage_ticks,"exit_reason":reason,"risk_points":abs(pos["entry_raw"]-pos["stop"])}); pos=None; cooldown=ts+pd.Timedelta(minutes=p.cooldown_minutes); continue
        if pos is None and pending is not None:
            if i>pending["expires_i"] or hh>"15:30": pending=None
            elif i>pending["signal_i"]:
                side=pending["side"]; trig=pending["trigger"]; filled=(row.high>=trig) if side=="long" else (row.low<=trig)
                if filled:
                    raw_entry=max(trig,float(row.open)) if side=="long" else min(trig,float(row.open)); entry_fill=raw_entry+slip if side=="long" else raw_entry-slip; pos={**pending,"entry_time":ts,"entry_raw":raw_entry,"entry_fill":entry_fill}; day_count[day]+=1; pending=None; same=None; reason=None
                    if side=="long":
                        if row.low<=pos["stop"]: same,reason=pos["stop"],"stop_same_bar"
                        elif row.high>=pos["target"]: same,reason=pos["target"],"target_same_bar"
                    else:
                        if row.high>=pos["stop"]: same,reason=pos["stop"],"stop_same_bar"
                        elif row.low<=pos["target"]: same,reason=pos["target"],"target_same_bar"
                    if same is not None:
                        exit_fill=same-slip if side=="long" else same+slip; direction=1 if side=="long" else -1; gross=direction*(same-pos["entry_raw"])*contract.point_value; net=direction*(exit_fill-pos["entry_fill"])*contract.point_value-contract.round_trip_fee; trades.append({"side":side,"signal_time":pos["signal_time"],"entry_time":ts,"exit_time":ts,"entry_raw":pos["entry_raw"],"entry_fill":pos["entry_fill"],"stop":pos["stop"],"target":pos["target"],"exit_raw":same,"exit_fill":exit_fill,"gross_pnl":gross,"net_pnl":net,"fees":contract.round_trip_fee,"slippage_ticks_each_side":slippage_ticks,"exit_reason":reason,"risk_points":abs(pos["entry_raw"]-pos["stop"])}); pos=None; cooldown=ts+pd.Timedelta(minutes=p.cooldown_minutes)
                    continue
        if pos is not None or pending is not None: continue
        if hh<"09:35" or hh>"15:30" or day_count[day]>=p.max_trades_day or (cooldown is not None and ts<cooldown): continue
        side="long" if bool(row.long_setup) else ("short" if bool(row.short_setup) else None)
        if side is None: continue
        eb=p.entry_buffer_ticks*contract.tick_size; sb=p.stop_buffer_ticks*contract.tick_size
        if side=="long": trigger=float(row.high+eb); stop=float(row.m5_swing_low-sb); risk=trigger-stop; target=trigger+p.risk_reward*risk
        else: trigger=float(row.low-eb); stop=float(row.m5_swing_high+sb); risk=stop-trigger; target=trigger-p.risk_reward*risk
        if not np.isfinite(risk) or risk<p.min_stop_points or risk>p.max_stop_points: continue
        pending={"side":side,"signal_time":ts,"signal_i":i,"expires_i":i+p.expiry_bars,"trigger":trigger,"stop":stop,"target":target}
    return pd.DataFrame(trades)

def stats(tr):
    if tr.empty: return {"trades":0,"wins":0,"win_rate":0.0,"net_pnl":0.0,"gross_pnl":0.0,"avg_net":0.0,"profit_factor":0.0,"max_drawdown":0.0,"median_net":0.0}
    pnl=tr.net_pnl.astype(float); wins=pnl[pnl>0]; losses=pnl[pnl<0]; eq=pnl.cumsum(); dd=eq-eq.cummax(); pf=float(wins.sum()/abs(losses.sum())) if len(losses) and losses.sum()!=0 else (999.0 if len(wins) else 0.0)
    return {"trades":int(len(tr)),"wins":int((pnl>0).sum()),"win_rate":float((pnl>0).mean()),"net_pnl":float(pnl.sum()),"gross_pnl":float(tr.gross_pnl.sum()),"avg_net":float(pnl.mean()),"profit_factor":pf,"max_drawdown":float(-dd.min()),"median_net":float(pnl.median())}

def start_day(d): return pd.Timestamp(f"{d} 00:00:00",tz="America/New_York").tz_convert("UTC")
def end_day(d): return pd.Timestamp(f"{d} 23:59:59",tz="America/New_York").tz_convert("UTC")

def evaluate(symbol,tick_path,one_path,outdir,point_value):
    c=Contract(symbol,point_value); tick=load_csv(tick_path); df30=resample(tick,"30s"); test_start=df30.index.min(); one=load_csv(one_path); warm=one[one.index<test_start]; base=pd.concat([warm,df30]).sort_index(); base=base[~base.index.duplicated(keep="last")]; feats=build_base_features(base); days=sorted(set(df30.index[df30.index>=test_start].tz_convert("America/New_York").date)); split=max(5,int(len(days)*0.60)); dev_days=days[:split]; hold_days=days[split:]; dev_start,dev_end=start_day(dev_days[0]),end_day(dev_days[-1]); hold_start,hold_end=start_day(hold_days[0]),end_day(hold_days[-1]); rows=[]
    for rr,vm,pb,vw in itertools.product([1.25,1.5,1.75,2.0],[0.90,1.00,1.10],[0.30,0.45,0.60],[True,False]):
        p=Params(risk_reward=rr,volume_multiple=vm,pullback_atr=pb,require_vwap=vw); tr=run_engine(add_setups(feats,p),c,p,1,dev_start,dev_end); s=stats(tr); rows.append({**asdict(p),**{f"dev_{k}":v for k,v in s.items()}})
    grid=pd.DataFrame(rows); eligible=grid[(grid.dev_trades>=12)&(grid.dev_profit_factor>1)&(grid.dev_avg_net>0)]; pool=eligible if not eligible.empty else grid[grid.dev_trades>=5]; pool=pool if not pool.empty else grid; score=pool.dev_avg_net*np.sqrt(pool.dev_trades.clip(lower=1)); best=pool.loc[score.idxmax()]; pbest=Params(risk_reward=float(best.risk_reward),volume_multiple=float(best.volume_multiple),pullback_atr=float(best.pullback_atr),require_vwap=bool(best.require_vwap)); fbest=add_setups(feats,pbest); dev_tr=run_engine(fbest,c,pbest,1,dev_start,dev_end); hold_tr=run_engine(fbest,c,pbest,1,hold_start,hold_end); all_tr=run_engine(fbest,c,pbest,1,test_start,df30.index.max()); stress=[]
    for sl in [0,1,2,3]: stress.append({"slippage_ticks_each_side":sl,**stats(run_engine(fbest,c,pbest,sl,test_start,df30.index.max()))})
    wf=[]; wf_tr=[]
    for fold,(train_frac,test_frac) in enumerate([(0.50,0.75),(0.75,1.00)],1):
        train_n=max(5,int(len(days)*train_frac)); test_n=max(train_n+1,int(len(days)*test_frac)); train_days=days[:train_n]; test_days=days[train_n:test_n]
        if not test_days: continue
        cand=[]
        for rr,vm,pb,vw in itertools.product([1.25,1.5,1.75,2.0],[0.90,1.00,1.10],[0.30,0.45,0.60],[True,False]):
            pp=Params(risk_reward=rr,volume_multiple=vm,pullback_atr=pb,require_vwap=vw); tt=run_engine(add_setups(feats,pp),c,pp,1,start_day(train_days[0]),end_day(train_days[-1])); cand.append((pp,stats(tt)))
        viable=[z for z in cand if z[1]["trades"]>=8 and z[1]["avg_net"]>0 and z[1]["profit_factor"]>1]; cp=viable or [z for z in cand if z[1]["trades"]>=4] or cand; pp,train_s=max(cp,key=lambda z:z[1]["avg_net"]*math.sqrt(max(z[1]["trades"],1))); tt=run_engine(add_setups(feats,pp),c,pp,1,start_day(test_days[0]),end_day(test_days[-1])); test_s=stats(tt); wf.append({"fold":fold,"train_start":str(train_days[0]),"train_end":str(train_days[-1]),"test_start":str(test_days[0]),"test_end":str(test_days[-1]),**asdict(pp),**{f"train_{k}":v for k,v in train_s.items()},**{f"test_{k}":v for k,v in test_s.items()}}); 
        if not tt.empty: tt=tt.copy(); tt["fold"]=fold; wf_tr.append(tt)
    sd=outdir/symbol; sd.mkdir(parents=True,exist_ok=True); grid.sort_values(["dev_avg_net","dev_profit_factor"],ascending=False).to_csv(sd/"parameter_grid.csv",index=False); pd.DataFrame(stress).to_csv(sd/"slippage_stress.csv",index=False); dev_tr.to_csv(sd/"development_trades.csv",index=False); hold_tr.to_csv(sd/"holdout_trades.csv",index=False); all_tr.to_csv(sd/"all_trades.csv",index=False); pd.DataFrame(wf).to_csv(sd/"walk_forward.csv",index=False); 
    if wf_tr: pd.concat(wf_tr).to_csv(sd/"walk_forward_trades.csv",index=False)
    report={"symbol":symbol,"source":"axb0306/cme-futures-ohlc (TopstepX / ProjectX Gateway API)","tick_rows":int(len(tick)),"bars_30s":int(len(df30)),"tick_start":str(df30.index.min()),"tick_end":str(df30.index.max()),"sessions":len(days),"development_sessions":len(dev_days),"holdout_sessions":len(hold_days),"development_dates":[str(dev_days[0]),str(dev_days[-1])],"holdout_dates":[str(hold_days[0]),str(hold_days[-1])],"commission_round_trip":c.round_trip_fee,"point_value":c.point_value,"tick_size":c.tick_size,"baseline_slippage_ticks_each_side":1,"best_params":asdict(pbest),"development":stats(dev_tr),"holdout":stats(hold_tr),"full_period":stats(all_tr),"stress":stress,"walk_forward":wf}; (sd/"report.json").write_text(json.dumps(report,indent=2,default=str)); print(json.dumps(report,indent=2,default=str)); return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--data",default="data"); ap.add_argument("--out",default="results"); a=ap.parse_args(); data=Path(a.data); out=Path(a.out); out.mkdir(parents=True,exist_ok=True); combined=[]
    for sym,pv in [("M2K",5.0),("RTY",50.0)]: combined.append(evaluate(sym,next(data.glob(f"{sym}_tick_*.csv")),next(data.glob(f"{sym}_1min_*.csv")),out,pv))
    (out/"combined_report.json").write_text(json.dumps(combined,indent=2,default=str))
if __name__=="__main__": main()
