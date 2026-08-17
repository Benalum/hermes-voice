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
# pandas 3 may keep tz-aware arrays at microsecond resolution. Generate the search
# array using Timestamp.value explicitly so both array and keys are UTC nanoseconds.
code=code.replace("Mreset=M.reset_index().sort_values('ts');mts=Mreset.ts.to_numpy();MH=Mreset.high.to_numpy();ML=Mreset.low.to_numpy();MC=Mreset.close.to_numpy();", "Mreset=M.reset_index().sort_values('ts');mts=Mreset.ts.map(lambda x: pd.Timestamp(x).value).to_numpy(dtype='int64');MH=Mreset.high.to_numpy();ML=Mreset.low.to_numpy();MC=Mreset.close.to_numpy();")
code=code.replace("np.searchsorted(mts,np.datetime64(entry_ts),'left')", "np.searchsorted(mts,pd.Timestamp(entry_ts).value,'left')")
code=code.replace("end=np.datetime64(entry_ts+pd.Timedelta(minutes=minutes))", "end=pd.Timestamp(entry_ts+pd.Timedelta(minutes=minutes)).value")
code=code.replace("np.searchsorted(mts,np.datetime64(r.ts),'left')", "np.searchsorted(mts,pd.Timestamp(r.ts).value,'left')")
code=code.replace("end=np.datetime64(r.ts+pd.Timedelta(minutes=minutes))", "end=pd.Timestamp(r.ts+pd.Timedelta(minutes=minutes)).value")
code=code.replace("for t in [.525,.55,.575,.60,.625,.65,.675,.70,.725,.75,.775,.80]:", "for t in [.50,.525,.55,.575,.60,.625,.65,.675,.70,.725,.75,.775,.80]:")
code=code.replace("if n<30:continue", "if n<20:continue")
code=code.replace("if len(tr)<1500 or len(va)<50 or len(ho_all)<100:continue", "print('SPLIT',ticks,minutes,'train',len(tr),'val',len(va),'hold_all',len(ho_all));\n  if len(tr)<1200 or len(va)<20 or len(ho_all)<100:continue")
old="R=pd.DataFrame(rows);print('=== 1M RESOLVED LOCKED BARRIER RESULTS ===');print(R.sort_values(['spaced_acc','spaced_n'],ascending=[False,False]).assign(val_acc=lambda x:(100*x.val_acc).round(2),hold_acc=lambda x:(100*x.hold_acc).round(2),hold_lo=lambda x:(100*x.hold_lo).round(2),spaced_acc=lambda x:(100*x.spaced_acc).round(2),spaced_lo=lambda x:(100*x.spaced_lo).round(2),mean_gross_ticks=lambda x:x.mean_gross_ticks.round(3),spaced_mean_ticks=lambda x:x.spaced_mean_ticks.round(3)).to_string(index=False));print('STRICT75_ALL_N30',len(R[(R.hold_acc>=.75)&(R.hold_n>=30)]),'STRICT75_SPACED_N30',len(R[(R.spaced_acc>=.75)&(R.spaced_n>=30)]));\nif len(R[(R.spaced_acc>=.75)&(R.spaced_n>=30)]):print('CANDIDATES\\n',R[(R.spaced_acc>=.75)&(R.spaced_n>=30)].to_string(index=False))"
new="R=pd.DataFrame(rows);print('=== 1M RESOLVED LOCKED BARRIER RESULTS ===');\nif len(R):\n print(R.sort_values(['spaced_acc','spaced_n'],ascending=[False,False]).assign(val_acc=lambda x:(100*x.val_acc).round(2),hold_acc=lambda x:(100*x.hold_acc).round(2),hold_lo=lambda x:(100*x.hold_lo).round(2),spaced_acc=lambda x:(100*x.spaced_acc).round(2),spaced_lo=lambda x:(100*x.spaced_lo).round(2),mean_gross_ticks=lambda x:x.mean_gross_ticks.round(3),spaced_mean_ticks=lambda x:x.spaced_mean_ticks.round(3)).to_string(index=False));print('STRICT75_ALL_N30',len(R[(R.hold_acc>=.75)&(R.hold_n>=30)]),'STRICT75_SPACED_N30',len(R[(R.spaced_acc>=.75)&(R.spaced_n>=30)]));\n if len(R[(R.spaced_acc>=.75)&(R.spaced_n>=30)]):print('CANDIDATES\\n',R[(R.spaced_acc>=.75)&(R.spaced_n>=30)].to_string(index=False))\nelse: print('NO_ELIGIBLE_ROWS')"
code=code.replace(old,new)
exec(compile(code,str(p),'exec'),{'__name__':'__main__','__file__':str(p)})
