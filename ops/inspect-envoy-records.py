import subprocess
queries=["SELECT quit FROM player_characters WHERE id=50000001;","SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ '(skill|spell|road|passive|talent|special)';","SELECT spellmaster_id,spellmaster_id & 65535,spell_level FROM player_spells WHERE player_id=50000001 ORDER BY spellmaster_id;"]
for q in queries:
 r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d','FFDB1','-c',q],text=True,capture_output=True,cwd='/tmp');print(r.stdout,r.stderr)
