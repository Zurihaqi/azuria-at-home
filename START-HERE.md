# Start your Aura Kingdom server

## Web dashboard

Double-click **Start Dashboard.cmd**, then open **http://127.0.0.1:8765**. The dashboard is local to this PC and can start the VM/game, manage players and mall listings, schedule mall sales, and create backups. Your separate admin login is in **private/dashboard/LOGIN.txt**. Keep the dashboard process running for scheduled sales. See **dashboard/README.md** for details.

## Play the game

1. Keep Tailscale connected on Windows.
2. Double-click **Start Server.cmd** in this folder. It starts the VM if needed and starts the game services.
3. Allow about one minute for the game channel to finish loading.
4. Open **Play Aura Kingdom.lnk** (Game.exe), then log in normally.

Alternatively, open VirtualBox, select **AuraKingdom-V15**, and click **Start**. PostgreSQL, Tailscale, and the game services are enabled to start automatically inside the VM. You do not need to log in at the Linux console.

Keep Windows and the VM running while you or friends play. Passwords are saved in `private/game-accounts.json`. Playerone and Zrymund have GM privilege 5; the game password is unchanged.

To check or start services manually, open PowerShell in this folder:

```powershell
python ops/vm.py run 'systemctl status aurakingdom --no-pager'
python ops/vm.py run 'systemctl start aurakingdom'
```

To stop game services after everyone logs out:

```powershell
python ops/vm.py run 'systemctl stop aurakingdom'
```

Do not rerun fullinstaller.sh: it drops the existing game databases.

Project cleanup on 29 October 2026 removed obsolete downloads and the unused
incomplete clean-client copy. Keep using the existing Play shortcut. Details and
the removal inventory are in `docs/PROJECT-CLEANUP.md` and `docs/project-cleanup.json`.

The custom mall is under **Item Mall → AP → Gear Catalog**. It includes equipment by type, costumes by slot, Eidolon keys, and mounts. Enhanced purchases and the latest character unlocks still need the player's in-game validation; see `docs/expanded-mall-deployment.json`.
