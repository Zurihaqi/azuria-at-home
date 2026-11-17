"""Compare client Sky Tower scene files with the running server and original ZIP CRCs."""
from pathlib import Path
import hashlib,json,re,sys,zlib
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT/'ops/runtime'))
import paramiko
CLIENT=ROOT/'client/Requiem Aurakingdom';OUT=ROOT/'staging/tower-scenes';OUT.mkdir(exist_ok=True)
archive=json.loads((ROOT/'docs/v15-original-archive.json').read_text())['files'];expected={x['name'].split('/',1)[1].lower():x for x in archive}
ssh=paramiko.SSHClient();ssh.load_host_keys(str(ROOT/'private/known_hosts'));key=paramiko.Ed25519Key.from_private_key_file(str(ROOT/'private/vm_ed25519'),password='""');ssh.connect('127.0.0.1',port=22222,username='root',pkey=key,look_for_keys=False,allow_agent=False)
manifest={'source':'Running V15 server Data/scene; original matching client ZIP CRCs independently checked','files':[],'missing_assets':[]}
try:
 with ssh.open_sftp() as sftp:
  for ident in range(701,751):
   name=f'S{ident}.ini';remote='/root/hxsy/Data/scene/'+name
   try:server=sftp.open(remote,'rb').read()
   except OSError:continue
   target=CLIENT/'data/scene'/name;old=target.read_bytes();row=server.splitlines()[1].decode('ascii').split(',');assert row[0].lower().endswith('.nif') and re.fullmatch('V[0-9]+',row[3]),(name,row)
   model=row[0].rsplit('.',1)[0];smp=row[4]
   assets=[f'map/model/{model}/{row[0]}',f'map/sknodemap/{smp}',f'map/sknodemap/{model}.pgp']
   for asset in assets:
    if not (CLIENT/asset).exists():manifest['missing_assets'].append({'scene':name,'path':asset})
   ref=expected.get(('data/scene/'+name).lower());crc=f'{zlib.crc32(server):08x}'
   item={'name':name,'before_sha256':hashlib.sha256(old).hexdigest(),'after_sha256':hashlib.sha256(server).hexdigest(),'client_geometry':old.splitlines()[1].decode('ascii'),'server_geometry':server.splitlines()[1].decode('ascii'),'original_zip_crc':ref['crc'] if ref else None,'server_crc':crc,'matches_original':crc==ref['crc'] if ref else None,'changed':old!=server}
   manifest['files'].append(item);(OUT/name).write_bytes(server)
 assert not manifest['missing_assets'],manifest['missing_assets']
 (ROOT/'docs/tower-scenes-manifest.json').write_text(json.dumps(manifest,indent=2))
 print(json.dumps({'scenes_checked':len(manifest['files']),'changed':sum(x['changed'] for x in manifest['files']),'matches_original_archive':sum(x['matches_original'] is True for x in manifest['files']),'missing_assets':manifest['missing_assets'],'geometry_mismatches':[{'name':x['name'],'client':x['client_geometry'],'server':x['server_geometry']} for x in manifest['files'] if x['client_geometry']!=x['server_geometry']]},indent=2))
finally:ssh.close()
