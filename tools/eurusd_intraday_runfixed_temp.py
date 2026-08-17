from pathlib import Path
p=Path('tools/eurusd_intraday_75_temp.py')
code=p.read_text()
code=code.replace("pd.Timestamp('2024-08-01',tz='UTC')","pd.Timestamp('2024-09-15',tz='UTC')")
code=code.replace("def models():return {","df[FEATURES]=df[FEATURES].replace([np.inf,-np.inf],np.nan)\n\ndef models():return {")
exec(compile(code,str(p),'exec'),{'__name__':'__main__','__file__':str(p)})
