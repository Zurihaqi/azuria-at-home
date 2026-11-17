"""Rebuild a separate baseline client using only CRC-matching original ZIP members."""
from pathlib import Path, PurePosixPath
import concurrent.futures, hashlib, importlib.util, json, os, shutil, sys, time, zipfile, zlib
ROOT=Path(__file__).resolve().parent.parent
OLD=ROOT/'client/Requiem Aurakingdom'
NEW=ROOT/'client/Aura Kingdom V15 Clean'
STAGED=ROOT/'staging/v15-original/Aura Kingdom v15 Unpacked'
REPORT=ROOT/'docs/clean-client-build.json'
manifest=json.loads((ROOT/'docs/v15-original-archive.json').read_text())

def relative(name):
    p=PurePosixPath(name.replace('\\','/'))
    if p.parts[0]!='Aura Kingdom v15 Unpacked' or '..' in p.parts:raise ValueError('Unsafe archive path')
    return Path(*p.parts[1:])

def crc(path):
    value=0
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):value=zlib.crc32(block,value)
    return f'{value&0xffffffff:08x}'

def check(entry,path):
    return path.is_file() and path.stat().st_size==entry['size'] and crc(path)==entry['crc']

def reuse(entry):
    rel=relative(entry['name']);target=NEW/rel
    if check(entry,target):return 'verified'
    candidates=[STAGED/rel,OLD/rel]
    if rel.parts[0].lower()=='base':candidates.append(OLD/Path(*rel.parts[1:]))
    for candidate in candidates:
        if check(entry,candidate):
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(candidate,target)
            return 'copied'
    return 'download'

if __name__=='__main__':
    NEW.mkdir(exist_ok=True)
    files=[e for e in manifest['files'] if not e['name'].endswith('/')]
    previous=json.loads(REPORT.read_text()) if '--fetch-only' in sys.argv else None
    report=previous or dict(source=manifest['source'],destination=str(NEW),total=len(files),copied=0,verified=0,download=[],complete=False)
    if previous:
        files=previous['download'];report['download']=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(reuse,e):e for e in files}
        for n,f in enumerate(concurrent.futures.as_completed(futures),1):
            e=futures[f];result=f.result()
            if result=='download':report['download'].append(e)
            else:report[result]+=1
            if n%5000==0:print(f'Checked {n}/{len(files)}; {len(report["download"])} original files needed',flush=True)
    report['download_bytes']=sum(e['packed'] for e in report['download'])
    REPORT.write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(reused=report['copied']+report['verified'],download_files=len(report['download']),download_bytes=report['download_bytes'])),flush=True)
    if not any(x in sys.argv for x in ['--fetch','--fetch-only']):raise SystemExit(0)
    spec=importlib.util.spec_from_file_location('megazip',ROOT/'ops/inspect-v15-client.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    report['downloaded']=[];report['failed']=[]
    # One archive connection per worker caches its central directory; no shared seek cursor.
    local=__import__('threading').local()
    def fetch_cached(entry):
        if not hasattr(local,'archive'):local.archive=zipfile.ZipFile(mod.MegaFile())
        data=local.archive.read(entry['name'])
        assert len(data)==entry['size'] and f'{zlib.crc32(data)&0xffffffff:08x}'==entry['crc']
        target=NEW/relative(entry['name']);target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_name(target.name+'.download');temporary.write_bytes(data);temporary.replace(target)
        return dict(name=entry['name'],sha256=hashlib.sha256(data).hexdigest())
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(fetch_cached,e):e for e in sorted(report['download'],key=lambda x:x['name'])}
        for n,f in enumerate(concurrent.futures.as_completed(futures),1):
            e=futures[f]
            try:report['downloaded'].append(f.result())
            except Exception as exc:report['failed'].append(dict(name=e['name'],error=str(exc)))
            if n%20==0 or n==len(futures):
                REPORT.write_text(json.dumps(report,indent=2));print(f'Downloaded/checked {n}/{len(futures)} original files; failed={len(report["failed"])}',flush=True)
    report['complete']=not report['failed']
    REPORT.write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(complete=report['complete'],downloaded=len(report['downloaded']),failed=report['failed'])),flush=True)
