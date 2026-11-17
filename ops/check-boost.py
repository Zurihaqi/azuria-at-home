import subprocess
def query(db,text):
    r=subprocess.run(['runuser','-u','postgres','--','psql','-X','-d',db,'-c',text],capture_output=True,text=True,cwd='/tmp');print(r.stdout);print(r.stderr)
query('FFDB1','SELECT id,given_name,level,exp,gold,bind_gold,skill_point,quit FROM player_characters WHERE id=50000001;')
query('FFDB1',"SELECT state,count(*) FROM sys_mail_queue WHERE receiver_id=50000001 AND title='Endgame gear +30' GROUP BY state;")
query('FFDB1','SELECT id,item_id,strengthen,(strengthen>>11)&31 AS fortification_rank FROM equipment1 WHERE player_id=50000001 AND container_index=0 ORDER BY loc;')
query('FFDB1','SELECT count(*) AS mail_attachments FROM mailitem WHERE player_id=50000001;')
