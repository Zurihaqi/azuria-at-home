"""Read-only inspection, constrained to the isolated pilot database."""
import json
import subprocess as sp
from lab import assert_inside

assert_inside()

def query(text):
    return sp.check_output(['runuser', '-u', 'postgres', '--', 'psql', '-h',
        '/run/postgresql', '-X', '-At', '-d', 'FFDB1', '-c', text], cwd='/').decode()

print(query("SELECT id,given_name,node_id,x,y,z,level,quit,account_id,privilege,state_flags,eudemon_level,survival_ghost,revive_area_id,last_normal_area_id FROM player_characters WHERE account_id=2421"))
print(query("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(stream|revive|buff|enchant|spell|tutorial)'"))
for table in ['beginner_tutorial','player_enchants','node_stream']:
    print(table, query(f"SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='{table}' ORDER BY ordinal_position"))
print('enchant rows', query('SELECT row_to_json(t) FROM player_enchants t WHERE player_id=50000005'))
