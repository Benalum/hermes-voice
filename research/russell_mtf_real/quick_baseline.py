from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import russell_real_backtest as rb
from russell_fast_runner import run_engine_fast

rb.run_engine = run_engine_fast


def run_symbol(sym, pv, data, out):
    c = rb.Contract(sym, pv)
    p = rb.Params(risk_reward=1.5, volume_multiple=1.0, pullback_atr=0.45, require_vwap=True)
    tick = rb.load_csv(next(data.glob(f"{sym}_tick_*.csv")))
    bars30 = rb.resample(tick, "30s")
    start = bars30.index.min()
    one = rb.load_csv(next(data.glob(f"{sym}_1min_*.csv")))
    warm = one[one.index < start]
    base = pd.concat([warm, bars30]).sort_index()
    base = base[~base.index.duplicated(keep="last")]
    feats = rb.add_setups(rb.build_base_features(base), p)
    rth_days = sorted(set(
        bars30.index[(bars30.index.tz_convert("America/New_York").strftime("%H:%M") >= "09:30") &
                     (bars30.index.tz_convert("America/New_York").strftime("%H:%M") <= "16:00")]
        .tz_convert("America/New_York").date
    ))
    split = max(1, int(len(rth_days) * 0.60))
    dev = rth_days[:split]
    hold = rth_days[split:]
    full_end = bars30.index.max()
    results = {}
    for sl in [0,1,2,3]:
        tr = rb.run_engine(feats,c,p,sl,start,full_end)
        results[f"full_slip_{sl}"] = rb.stats(tr)
        if sl == 1:
            tr.to_csv(out/f"{sym}_all_trades.csv",index=False)
    dev_tr = rb.run_engine(feats,c,p,1,rb.start_day(dev[0]),rb.end_day(dev[-1]))
    hold_tr = rb.run_engine(feats,c,p,1,rb.start_day(hold[0]),rb.end_day(hold[-1])) if hold else pd.DataFrame()
    dev_tr.to_csv(out/f"{sym}_development_trades.csv",index=False)
    hold_tr.to_csv(out/f"{sym}_holdout_trades.csv",index=False)
    report = {
        "symbol":sym,"params":rb.asdict(p),"commission_round_trip":2.38,"slippage_baseline_ticks_each_side":1,
        "tick_rows":len(tick),"bars30":len(bars30),"start":str(start),"end":str(full_end),
        "rth_sessions":len(rth_days),"development_dates":[str(dev[0]),str(dev[-1])],
        "holdout_dates":[str(hold[0]),str(hold[-1])] if hold else [],
        "development":rb.stats(dev_tr),"holdout":rb.stats(hold_tr),"stress":results
    }
    return report


def main():
    data=Path("data"); out=Path("quick_results"); out.mkdir(exist_ok=True)
    reports=[run_symbol("M2K",5.0,data,out),run_symbol("RTY",50.0,data,out)]
    (out/"quick_report.json").write_text(json.dumps(reports,indent=2,default=str))
    print(json.dumps(reports,indent=2,default=str))

if __name__ == "__main__": main()
