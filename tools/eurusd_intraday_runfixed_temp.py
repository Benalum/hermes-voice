from pathlib import Path
p=Path('tools/eurusd_intraday_75_temp.py')
code=p.read_text()
code=code.replace("pd.Timestamp('2024-08-01',tz='UTC')","pd.Timestamp('2024-09-15',tz='UTC')")
code=code.replace("daily['prev_day_ret']=np.log(daily.day_close/daily.day_close.shift());daily['prev_range']=(daily.day_high-daily.day_low)/daily.day_close","daily['prev_day_ret']=np.log(daily.day_close.shift(1)/daily.day_close.shift(2));daily['prev_range']=(daily.day_high.shift(1)-daily.day_low.shift(1))/daily.day_close.shift(1)")
code=code.replace("trn=df[(df.ts<t0)&df[target].notna()]","trn=df[(df.ts<(t0-pd.Timedelta(hours=h)))&df[target].notna()]")
code=code.replace("train=df[df.ts<pd.Timestamp('2026-01-01',tz='UTC')].copy()","train=df[df.ts<(pd.Timestamp('2026-01-01',tz='UTC')-pd.Timedelta(hours=12))].copy()")
code=code.replace("def models():return {","df[FEATURES]=df[FEATURES].replace([np.inf,-np.inf],np.nan)\n\ndef models():return {")
exec(compile(code,str(p),'exec'),{'__name__':'__main__','__file__':str(p)})
