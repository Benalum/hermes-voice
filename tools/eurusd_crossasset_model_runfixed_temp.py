from pathlib import Path
p=Path('tools/eurusd_crossasset_intraday_75_temp.py')
code=p.read_text().replace("pd.Timestamp('2024-08-01',tz='UTC')","pd.Timestamp('2024-09-15',tz='UTC')")
code=code.split('# Locked 2026 rules')[0]
code=code.replace("def models():return {","e[FEATURES]=e[FEATURES].replace([np.inf,-np.inf],np.nan)\n\ndef models():return {")
exec(compile(code,str(p),'exec'),{'__name__':'__main__','__file__':str(p)})
