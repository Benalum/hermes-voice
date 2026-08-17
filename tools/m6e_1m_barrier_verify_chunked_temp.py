from pathlib import Path
p=Path('tools/m6e_1m_barrier_verify_temp.py')
code=p.read_text()
a=code.index('def load(sym):')
b=code.index("M=load('M6E=F')")
replacement='''def load(sym):
 chunks=[]
 cur=pd.Timestamp('2026-07-19',tz='UTC'); end=pd.Timestamp('2026-08-17',tz='UTC')
 while cur<end:
  nxt=min(cur+pd.Timedelta(days=6),end)
  p1=int(cur.timestamp());p2=int(nxt.timestamp())
  u=f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1m&events=history&includePrePost=true"
  r=requests.get(u,timeout=90,headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status();z=r.json()['chart']['result'][0];q=z['indicators']['quote'][0]
  chunks.append(pd.DataFrame({'ts':pd.to_datetime(z['timestamp'],unit='s',utc=True),'open':q['open'],'high':q['high'],'low':q['low'],'close':q['close'],'volume':q.get('volume',[None]*len(z['timestamp']))}))
  cur=nxt
 return pd.concat(chunks,ignore_index=True).dropna(subset=['open','high','low','close']).sort_values('ts').drop_duplicates('ts')
'''
code=code[:a]+replacement+code[b:]
# Use UTC epoch nanoseconds for path-search comparisons so tz-aware pandas timestamps
# never meet tz-naive numpy datetime64 values.
code=code.replace("Mreset=M.reset_index().sort_values('ts');mts=Mreset.ts.to_numpy();MH=Mreset.high.to_numpy();ML=Mreset.low.to_numpy();MC=Mreset.close.to_numpy();", "Mreset=M.reset_index().sort_values('ts');mts=Mreset.ts.astype('int64').to_numpy();MH=Mreset.high.to_numpy();ML=Mreset.low.to_numpy();MC=Mreset.close.to_numpy();")
code=code.replace("np.searchsorted(mts,np.datetime64(entry_ts),'left')", "np.searchsorted(mts,pd.Timestamp(entry_ts).value,'left')")
code=code.replace("end=np.datetime64(entry_ts+pd.Timedelta(minutes=minutes))", "end=pd.Timestamp(entry_ts+pd.Timedelta(minutes=minutes)).value")
code=code.replace("np.searchsorted(mts,np.datetime64(r.ts),'left')", "np.searchsorted(mts,pd.Timestamp(r.ts).value,'left')")
code=code.replace("end=np.datetime64(r.ts+pd.Timedelta(minutes=minutes))", "end=pd.Timestamp(r.ts+pd.Timedelta(minutes=minutes)).value")
exec(compile(code,str(p),'exec'),{'__name__':'__main__','__file__':str(p)})
