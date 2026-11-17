import subprocess as sp
from pathlib import Path
def q(sql):
    r=sp.run(['runuser','-u','postgres','--','psql','-X','-tA','-d','FFDB1'],input=sql,text=True,capture_output=True,cwd='/tmp',check=True)
    print(r.stdout)
q("SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND (table_name LIKE '%elf%' OR table_name LIKE '%partner%') ORDER BY table_name,ordinal_position;")
for name in ('S_Partner.ini','S_PartnerGrow.ini'):
    p=Path('/root/hxsy/Data/db')/name
    print(name, p.read_bytes()[:700].decode('cp950',errors='replace'))
