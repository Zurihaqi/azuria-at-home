import subprocess as sp
import json
from pathlib import Path
def q(sql):
 r=sp.run(['runuser','-u','postgres','--','psql','-X','-tA','-v','ON_ERROR_STOP=1','-d','FFDB1'],input=sql,text=True,capture_output=True,cwd='/tmp',check=True)
 return r.stdout.strip()
out={}
for key,sql in {
 'elf':"SELECT coalesce(json_agg(t ORDER BY elf_id),'[]') FROM elf t WHERE account_id=2419",
 'bank':"SELECT coalesce(json_agg(t ORDER BY elf_id),'[]') FROM elf_bank t WHERE account_id=2419",
 'house':"SELECT coalesce(json_agg(t ORDER BY elf_id),'[]') FROM elf_house t WHERE account_id=2419",
 'elf_columns':"SELECT json_agg(t ORDER BY ordinal_position) FROM (SELECT * FROM information_schema.columns WHERE table_name='elf')t",
 'sequences':"SELECT coalesce(json_agg(t),'[]') FROM pg_sequences t",
 'id_tables':"SELECT coalesce(json_agg(t),'[]') FROM (SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND (table_name ~ '(serial|unique|sequence)' OR column_name ~ '(elf_count|elf_num|eudemon_count|eudemon_num)'))t",
}.items():out[key]=json.loads(q(sql))
Path('/root/max-eidolons-inspection.json').write_text(json.dumps(out))
print(json.dumps(out))
