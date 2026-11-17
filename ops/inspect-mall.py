import subprocess
def query(text):
    r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d','FFAccount','-c',text],capture_output=True,text=True,cwd='/tmp');print(r.stdout);print(r.stderr)
query('\\d itemmall')
query('SELECT item_group,detail_type,money_unit,count(*) FROM itemmall GROUP BY item_group,detail_type,money_unit ORDER BY 1,2,3;')
query('SELECT * FROM itemmall ORDER BY item_group,detail_type,item_index LIMIT 4;')
