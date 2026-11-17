"""Read-only schema and level/map diagnostics for the requested bot work."""
import json
import re
import subprocess as sp

def query(sql):
    return sp.check_output(['runuser','-u','postgres','--','psql','-h','/var/run/postgresql',
        '-X','-qAt','-v','ON_ERROR_STOP=1','-d','FFDB1'],input=sql.encode(),cwd='/').decode().strip()

columns = json.loads(query("SELECT json_agg(json_build_object('name',column_name,'type',data_type)) FROM information_schema.columns WHERE table_name='player_characters'"))
print('appearance_columns', json.dumps([row for row in columns if re.search('sex|gender|hair|face|appear|look|race|color|style',row['name'],re.I)]))
print('levels_maps', query("SELECT json_agg(t) FROM (SELECT id,given_name,level,node_id,quit FROM player_characters WHERE id IN(50000001,50000002,50000003)) t"))
print('related_tables',query("SELECT json_agg(table_name) FROM information_schema.tables WHERE table_schema='public' AND table_name ~ '(party|team|appearance|look|style)'"))
