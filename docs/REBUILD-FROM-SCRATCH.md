# Rebuild From Scratch Runbook

This guide explains how to reconstruct the entire **Azuria-at-Home** environment on a fresh Windows PC starting from this repository and your offline base archives.

---

## 1. Prerequisites & Base Archives

Place the following local files (excluded from Git) into the workspace:

1. **Python Dependencies (Windows Host):**
   ```powershell
   pip install -r requirements.txt --target ops/runtime
   ```
2. **Base Archives (`downloads/`):**
   Verify SHA-256 hashes against [docs/release-sha256.json](release-sha256.json):
   - `downloads/debian-11.11.0-amd64-netinst.iso` (Debian 11 Bullseye netinst)
   - `downloads/server/hxsy.zip` (SHA-256: `ff7e039fe3300050d85f1d2c6c3abcdda2f84c076217343a82246ad3953f2b0d`)
   - `downloads/bins/BINS.rar` (SHA-256: `92b80a3a668fb2bce434f7f2fd575e67fe2a5c54d09d7d910ae120f872ce9664`)
3. **Game Client (`client/Requiem Aurakingdom/`):**
   - Extract the v15 client (`game.bin` PE version `15.0.1.16`) into `client/Requiem Aurakingdom/`.
4. **Private Credentials (`private/`):**
   - Create `private/vm_ed25519` (SSH key pair) and `private/known_hosts`.
   - Create `private/network-config.json`:
     ```json
     {
       "server_vpn_ip": "100.64.0.10",
       "owner_vpn_ip": "100.64.0.1"
     }
     ```

---

## 2. Fast Path: 10-Minute Snapshot Restore (Recommended)

If you kept a personal backup bundle from `private/backups/<timestamp>/` (`server.tgz` + `FFAccount.dump`, `FFDB1.dump`, `FFMember.dump` + `globals.sql`):

1. Provision a Debian 11 VM in VirtualBox (`AuraKingdom-V15`, 4 vCPU, 4 GiB RAM, NAT port-forwarding `127.0.0.1:22222 -> :22`).
2. Update `ops/ak-firewall.nft` with your Tailscale IPv4 address and run:
   ```bash
   bash ops/prepare-guest.sh
   ```
3. Restore the PostgreSQL roles and three databases:
   ```bash
   runuser -u postgres -- psql -f globals.sql
   for db in FFAccount FFDB1 FFMember; do
       runuser -u postgres -- createdb "$db"
       runuser -u postgres -- pg_restore --exit-on-error -d "$db" "$db.dump"
   done
   ```
4. Extract `/root/hxsy` from `server.tgz`, install the systemd unit (`aurakingdom.service`), and start the server:
   ```powershell
   python ops/vm.py run "systemctl enable --now aurakingdom"
   ```

---

## 3. Full Rebuild Path: Step-by-Step Patch Pipeline

If rebuilding from the unmodified base `hxsy.zip` and `BINS.rar` archives without a prior backup:

### Step 1 — Guest OS, Firewall & Tailscale
Inside the fresh Debian 11 VM:
```bash
bash /path/to/ops/prepare-guest.sh
```
This configures archived Debian 11 security repositories, installs PostgreSQL 13, loads the restrictive `ak_guard` nftables firewall (`ops/ak-firewall.nft`), and brings up Tailscale.

### Step 2 — Base Game Server Installation
Run the non-destructive wrapper around `vendor/AKF/fullinstaller.sh`:
```bash
bash /path/to/ops/install-game.sh /root/hxsy.zip
```
This configures `vsyscall=emulate`, `LANG=C` / `LC_ALL=C` for legacy static glibc compatibility, imports the base `FFAccount`, `FFDB1`, and `FFMember` schemas, and patches the server IP into `WorldServer` and `ZoneServer`.

### Step 3 — Binary Instrumentation & ELF Hooks (Unicorn-Verified)
Apply the four binary patches in sequence from the Windows host:

1. **Null `ifa_addr` Tunnel Guard (`WorldServer` & `ZoneServer`):**
   Prevents segfaults when enumerating point-to-point TUN/Tailscale interfaces that have null `ifa_addr` pointers:
   ```powershell
   python ops/patch-null-ifaddrs.py
   ```
2. **+30 Fortification & 5-Star Mall Delivery Hook (`ZoneServer`):**
   Hooks `CNE_ZW_ZoneServerItemMallReceieveAttempt::Execute` (`0x7c787f` and `0x7c7f10`) to auto-fortify eligible equipment and grant 5-star evolution upon mall claim:
   ```powershell
   python ops/verify-mall-enhancement-hook.py
   python ops/patch-mall-enhancement.py
   ```
3. **F2P In-Memory Gold Debit Hook (`ZoneServer`):**
   Chains onto the delivery hook to call `CCharacter::GainCoins` in live ZoneServer memory so logout `SavePlayerCharacter` flushes do not overwrite SQL gold debits:
   ```powershell
   python ops/build-mall-debit-hook.py
   python ops/verify-mall-debit-hook.py
   python ops/patch-mall-debit.py
   ```
4. **32-Bit Damage Clamp Expansion (`ZoneServer`):**
   Raises the 21 genuine `99,999,999` (`0x05F5E0FF`) damage/HP clamp immediates to `INT32_MAX` (`0x7FFFFFFF`):
   ```powershell
   python ops/build-damage-cap-patch.py
   python ops/verify-damage-cap-patch.py
   python ops/patch-damage-cap.py
   ```

### Step 4 — 19,649-Item F2P Item Mall & `dblink` Billing
Install the 43-category F2P item mall catalog and rewrite `FFMember` billing functions (`get_point_info`, `req_buy_item`) to charge in-game character Gold and Bind Gold:
```powershell
python ops/install-full-mall.py
```

### Step 5 — Client Compatibility & Custom Content
Apply client table alignments and custom expansions:
- Align `client/Requiem Aurakingdom/connect.ini` and `connects.ini` to your VM's Tailscale IP (`:6543`) and `C_SysSetup.ini` revision to `001`.
- Apply the 44-category `game.bin` label vector expansion and `T_TextIndex.ini` Gold branding.
- *(Optional)* Deploy custom content packages (`ops/deploy-sovereign-v2.py`, `ops/deploy-extra-eidolons.py`, `ops/deploy-guitar-switch.py`, `ops/restore-original-soundtrack.py`).

### Step 6 — Backups, Bots & Astral Control Dashboard
1. Install the automated daily backup service (`ops/backup.sh`, `ops/ak-backup.service`, `ops/ak-backup.timer`).
2. Provision and deploy autonomous bots (`bots/provision_normal.py`, `bots/deploy_activity.py`).
3. Launch the local **Astral Control** web console via `Start Dashboard.cmd` (`http://127.0.0.1:8765`).
