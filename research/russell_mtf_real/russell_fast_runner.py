from __future__ import annotations
import numpy as np
import pandas as pd
import russell_real_backtest as rb


def run_engine_fast(f, contract, p, slippage_ticks, trade_start, trade_end=None):
    # Same conservative fill rules as the reference engine, but iterate only the
    # RTH execution window and use itertuples instead of repeated DataFrame .loc.
    mask = f.index >= trade_start
    if trade_end is not None:
        mask &= f.index <= trade_end
    loc = f.index.tz_convert("America/New_York")
    hhmm = loc.strftime("%H:%M")
    mask &= (hhmm >= "09:35") & (hhmm <= "16:00")
    x = f.loc[mask]
    if x.empty:
        return pd.DataFrame()

    trades=[]; pending=None; pos=None; cooldown=None; day_count={}
    slip = slippage_ticks * contract.tick_size
    rows = list(x.itertuples())
    for i,row in enumerate(rows):
        ts=row.Index; local=ts.tz_convert("America/New_York"); hh=local.strftime("%H:%M"); day=local.date(); day_count.setdefault(day,0)
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
                exit_fill=raw-slip if side=="long" else raw+slip; direction=1 if side=="long" else -1
                gross=direction*(raw-pos["entry_raw"])*contract.point_value
                net=direction*(exit_fill-pos["entry_fill"])*contract.point_value-contract.round_trip_fee
                trades.append({"side":side,"signal_time":pos["signal_time"],"entry_time":pos["entry_time"],"exit_time":ts,"entry_raw":pos["entry_raw"],"entry_fill":pos["entry_fill"],"stop":pos["stop"],"target":pos["target"],"exit_raw":raw,"exit_fill":exit_fill,"gross_pnl":gross,"net_pnl":net,"fees":contract.round_trip_fee,"slippage_ticks_each_side":slippage_ticks,"exit_reason":reason,"risk_points":abs(pos["entry_raw"]-pos["stop"])}); pos=None; cooldown=ts+pd.Timedelta(minutes=p.cooldown_minutes); continue
        if pos is None and pending is not None:
            if day!=pending["day"] or i>pending["expires_i"] or hh>"15:30": pending=None
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
                        exit_fill=same-slip if side=="long" else same+slip; direction=1 if side=="long" else -1; gross=direction*(same-pos["entry_raw"])*contract.point_value; net=direction*(exit_fill-pos["entry_fill"])*contract.point_value-contract.round_trip_fee
                        trades.append({"side":side,"signal_time":pos["signal_time"],"entry_time":ts,"exit_time":ts,"entry_raw":pos["entry_raw"],"entry_fill":pos["entry_fill"],"stop":pos["stop"],"target":pos["target"],"exit_raw":same,"exit_fill":exit_fill,"gross_pnl":gross,"net_pnl":net,"fees":contract.round_trip_fee,"slippage_ticks_each_side":slippage_ticks,"exit_reason":reason,"risk_points":abs(pos["entry_raw"]-pos["stop"])}); pos=None; cooldown=ts+pd.Timedelta(minutes=p.cooldown_minutes)
                    continue
        if pos is not None or pending is not None: continue
        if hh>"15:30" or day_count[day]>=p.max_trades_day or (cooldown is not None and ts<cooldown): continue
        side="long" if bool(row.long_setup) else ("short" if bool(row.short_setup) else None)
        if side is None: continue
        eb=p.entry_buffer_ticks*contract.tick_size; sb=p.stop_buffer_ticks*contract.tick_size
        if side=="long": trigger=float(row.high+eb); stop=float(row.m5_swing_low-sb); risk=trigger-stop; target=trigger+p.risk_reward*risk
        else: trigger=float(row.low-eb); stop=float(row.m5_swing_high+sb); risk=stop-trigger; target=trigger-p.risk_reward*risk
        if not np.isfinite(risk) or risk<p.min_stop_points or risk>p.max_stop_points: continue
        pending={"side":side,"signal_time":ts,"signal_i":i,"expires_i":i+p.expiry_bars,"day":day,"trigger":trigger,"stop":stop,"target":target}
    return pd.DataFrame(trades)


if __name__ == "__main__":
    rb.run_engine = run_engine_fast
    rb.main()
