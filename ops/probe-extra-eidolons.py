"""Normal native collection/summoning checks, isolated lab only, no GM packets."""
import asyncio,json,struct,sys,time
from pathlib import Path
sys.path.insert(0,'/opt/ak-bot-prototype')
import wire
from wire import Reader
assert Path('/run/ak-bot-lab.json').is_file()
m=json.loads(Path('/run/extra-eidolon-manifest.json').read_text())
protocol=json.loads(Path('/run/pilot/zone-protocol.json').read_text())
active={};collection={};result=dict(collection=[],summons=[],errors=[]);worker=None;done=None
original=wire.Connection.receive
def elf(d):
 r=dict(slot=d.number('h'),id=d.number('I'),owner=d.number('i'),template=d.number('i'),hp=d.number('i'),
        work=d.number('h'),status=d.number('h'),spell_state=d.number('h'),name=d.text())
 d.number('Q');d.number('Q');r.update(level=d.number('b'),stars=d.number('h'),energy=d.number('i'));d.number('h')
 for _ in range(6):d.number('i')
 d.number('i');d.number('h');d.number('h')
 for _ in range(5):d.number('H')
 d.number('i');count=d.number('i');assert 0<=count<=1000,count
 for _ in range(count):d.number('i');d.number('i');d.number('h')
 d.number('h');d.number('Q');r['affection']=d.number('b');r['skills']=[d.number('h') for _ in range(3)]
 return r
def save():Path('/run/pilot/extra-eidolon-results.json').write_text(json.dumps(result,indent=2))
async def exercise(conn):
 try:
  await conn.send(protocol['CNE_CZ_ZoneServerQueryElfBankInfo'])
  await asyncio.sleep(3)
  have={r['template'] for r in active.values()}|set(collection)
  assert set(m['extra'])<=have,('Missing native records',sorted(set(m['extra'])-have))
  result['collection']=sorted(have);save()
  # Reuse active slot 0; normal account storage swaps, no teleports/grants.
  for index,ident in enumerate(m['extra']):
   if index<4:slot=index
   else:
    await conn.send(protocol['CNE_CZ_ZoneServerElfBankSwitch'],struct.pack('<bhh',0,0,29))
    await asyncio.sleep(.6)
    await conn.send(protocol['CNE_CZ_ZoneServerElfBankSwitch'],struct.pack('<bhh',1,index-4,0))
    await asyncio.sleep(.6);slot=0
   await conn.send(protocol['CNE_CZ_ZoneServerElfWork'],struct.pack('<hh',slot,1))
   await asyncio.sleep(2)
   await conn.send(protocol['CNE_CZ_ZoneServerEnterNodeElfInfo'])
   await asyncio.sleep(1)
   observed=active.get(slot)
   assert observed and observed['template']==ident and observed['status']==1,(ident,observed)
   assert observed['level']==99 and observed['stars']==4 and observed['affection']==10,observed
   result['summons'].append(dict(template=ident,slot=slot,status=observed['status'],skills=observed['skills']))
   print('Confirmed native summon',ident,flush=True);save()
   await conn.send(protocol['CNE_CZ_ZoneServerElfWork'],struct.pack('<hh',slot,0))
   await asyncio.sleep(6.5)
  result['passed']=True;save()
 except Exception as e:
  result['errors'].append(str(e));result['passed']=False;save();print('Eidolon test stopped:',str(e),flush=True)
 finally:done.set()
async def receive(conn):
 global worker
 packet,payload=await original(conn)
 peer=conn.writer.get_extra_info('peername')
 if not peer or peer[1]!=10020:return packet,payload
 if packet in (protocol['CNC_CZ_ClientEnterNodeElfInfo'],protocol['CNC_CZ_ClientElfCollectionInfo'],protocol['CNC_CZ_ClientElfBankInfo']):
  try:
   d=Reader(payload)
   if packet==protocol['CNC_CZ_ClientElfBankInfo']:d.number('B')
   kind=d.number('H');count=d.number('H');assert 0<=count<=1000
   records=[elf(d) for _ in range(count)];d.end()
   if packet==protocol['CNC_CZ_ClientEnterNodeElfInfo']:active.clear();active.update({r['slot']:r for r in records})
   else:collection.update({r['template']:r for r in records})
  except Exception as e:
   result['errors'].append('Snapshot decode: '+str(e));save();done.set()
 if packet==protocol['CNC_CZ_ClientMigrationDone'] and worker is None:
  worker=asyncio.create_task(exercise(conn))
 return packet,payload
wire.Connection.receive=receive
import probe_login as probe
async def main():
 global done
 done=asyncio.Event();task=asyncio.create_task(probe.main())
 try:await asyncio.wait_for(done.wait(),500)
 finally:
  if worker is not None and not worker.done():worker.cancel();await asyncio.gather(worker,return_exceptions=True)
  task.cancel();await asyncio.gather(task,return_exceptions=True);save()
asyncio.run(main())
raise SystemExit(0 if result.get('passed') else 1)
