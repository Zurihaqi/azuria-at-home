# Aura Kingdom Server Installer

An installer and management toolkit for the Aura Kingdom (hxsy) server files.
Everything is guided, translated into 10 languages, and designed so that a
first-time user can get a working server without touching a config file.

**Languages:** English · Deutsch · Русский · Français · 中文 (简体) · 한국어 · 日本語 · Português (PT/BR) · Türkçe

---

## Quick install

Connect to your server over SSH as `root` and run:

```bash
cd /root && curl -fsSLO https://raw.githubusercontent.com/MrDulgan/AKF/main/fullinstaller.sh && chmod +x fullinstaller.sh && ./fullinstaller.sh
```

The installer asks for your language, the address players will connect to, and
an administrator account. Everything else is automatic.

If `raw.githubusercontent.com` is blocked on your network, use the mirror:

```bash
cd /root && curl -fsSLO https://cdn.jsdelivr.net/gh/MrDulgan/AKF@main/fullinstaller.sh && chmod +x fullinstaller.sh && ./fullinstaller.sh
```

---

## Requirements

|                | Minimum | Recommended |
| -------------- | ------- | ----------- |
| CPU            | x86_64  | x86_64, 2 cores |
| Memory         | 1 GB (a swap file is offered) | 4 GB |
| Free disk      | 3 GB    | 10 GB |
| Access         | root    | root |

**Supported systems**

- Debian 11, 12, 13
- Ubuntu 20.04, 22.04, 24.04
- Rocky Linux / AlmaLinux / CentOS Stream 8, 9

The server binaries are x86_64 only. ARM machines (Oracle Ampere, Raspberry Pi,
Apple Silicon VMs, most "free tier" cloud instances) **cannot** run them, and the
installer stops with a clear message instead of failing halfway.

---

## What the installer does

| Step | Description |
| ---- | ----------- |
| System check | Architecture, kernel, memory, disk, connectivity, virtualisation |
| Address | Detects local and public IPs, warns about NAT and port forwarding |
| Packages | Installs only what is needed, per distribution |
| Locales | Generates `en_US.UTF-8` |
| PostgreSQL | Installs 13 from the PGDG repository; falls back to the newest available version and says so |
| Database security | Random 24-character password, `md5` authentication (required by the old client library the game binaries link against), local-only access by default |
| Firewall | Opens the game ports on UFW or firewalld |
| Server files | Downloads and verifies the archive, or uses a local one |
| Runtime libraries | Detects whether the binaries are 32- or 64-bit and installs the matching libraries |
| Databases | Creates `FFAccount`, `FFDB1`, `FFMember` and imports the dumps |
| Patching | Writes your IP into the binaries with an exact byte-level patch, keeps `.orig` backups |
| vsyscall | Adds `vsyscall=emulate` to the kernel command line, which the old binaries need |
| Verification | Checks the service, databases, binaries, shared libraries, kernel flags and ports |

At the end you get a summary with every credential, also written to
`<install-dir>/install-summary.txt` (mode `600`).

---

## Options

```
./fullinstaller.sh [options]

  --lang=CODE          en de ru fr zh ko ja pt pt_BR tr
  --ip=ADDRESS         Public address players will connect to
  --dir=PATH           Installation folder (default: /root/hxsy)
  --archive=PATH       Use a local server archive instead of downloading
  --archive-url=URL    Download the server archive from a direct HTTP(S) link
  --pg-version=N       PostgreSQL major version (default: 13)
  --admin-user=NAME    Create the GM account without prompting
  --admin-pass=PASS    Password for --admin-user
  --expose-db          Allow remote PostgreSQL connections
  --service            Install the systemd service
  --no-service         Do not install the systemd service
  --yes                Accept every confirmation
  --non-interactive    Never ask anything (implies --yes)
  --doctor             Only diagnose an existing installation
  --help               Show this text
```

### Unattended install

```bash
./fullinstaller.sh --non-interactive --lang=en --ip=203.0.113.10 \
                   --admin-user=gm --admin-pass=changeme123 --service
```

### Install from a local archive

Useful when the MEGA download keeps failing. Upload the archive yourself, then:

```bash
./fullinstaller.sh --archive=/root/hxsy.zip
```

---

## Running the server

```bash
/root/hxsy/start        # start every server and show a live status view
/root/hxsy/stop         # stop everything and archive the logs
```

`start` launches the six servers in order, writes a PID file per server, waits
until each one is actually listening, and then shows uptime, CPU and memory
usage. `CTRL+C` performs a clean shutdown. If a server crashes it is reported
immediately, and if all of them are gone the script exits with an error so
systemd can restart it.

### As a system service

If you let the installer create the service (or ran it with `--service`):

```bash
systemctl start aurakingdom
systemctl stop aurakingdom
systemctl restart aurakingdom
systemctl status aurakingdom
journalctl -u aurakingdom -f
```

---

## Accounts

```bash
/root/hxsy/account_creator.sh
```

A menu lets you create an account, change a password, change the point balance
(`pvalues`), or grant GM rights. It can also run unattended:

```bash
/root/hxsy/account_creator.sh --user=player1 --pass=secret123 --pvalues=1000
```

To use GM commands in the game, create a character first, then set `privilege`
to `5` for that character in the `player_characters` table of `FFDB1`.

---

## Troubleshooting

Run the built-in diagnosis first — it checks everything the installer set up and
reports what is broken:

```bash
/root/hxsy/fullinstaller.sh --doctor
```

**The server starts but nobody can connect.**
Check that you selected the right address during installation. If your machine
is behind a router or a cloud firewall, the public address must be reachable and
these TCP ports forwarded: `5567 5568 6543 7654 7777 7878 10021 10022`.
To change the address afterwards, re-run the installer.

**A server exits immediately.**
Almost always missing `vsyscall=emulate`. Verify with:

```bash
grep -o vsyscall=emulate /proc/cmdline
```

If it prints nothing, reboot — the installer already added it to the bootloader
and the setting only takes effect after a restart.

**`error while loading shared libraries`.**
The binaries are 32-bit and the 32-bit runtime is missing. `--doctor` names the
exact libraries. On Debian and Ubuntu:

```bash
dpkg --add-architecture i386 && apt-get update && apt-get install -y libc6:i386 libstdc++6:i386 zlib1g:i386
```

**The download fails.**
MEGA enforces daily transfer limits. Wait a few hours, or download the archive
on another machine, upload it to the server and run the installer with
`--archive=/root/hxsy.zip`.

**Authentication failure in the server logs.**
The game binaries only speak `md5` authentication. The installer configures
PostgreSQL accordingly; if you changed `password_encryption` to
`scram-sha-256` afterwards, change it back and reset the password.

**Anything else.**
The full log is at `/var/log/ak-installer.log`. Attach it when asking for help —
it contains every command the installer ran and its output.

---

## Files and locations

| Path | Purpose |
| ---- | ------- |
| `/root/hxsy` | Server files (configurable with `--dir`) |
| `/root/hxsy/install-summary.txt` | Credentials and paths, mode `600` |
| `/root/hxsy/Logs/` | Per-server output, startup logs, archived logs |
| `/root/hxsy/Logs/run/` | PID files |
| `/var/log/ak-installer.log` | Installer log |
| `/etc/ak-server.conf` | Install folder, language and IP, shared by all scripts |
| `/etc/systemd/system/aurakingdom.service` | Optional service unit |

Original configuration files are never overwritten without a backup: `postgresql.conf`,
`pg_hba.conf` and `/etc/default/grub` get an `.ak-backup` copy, and patched
binaries keep an `.orig` copy next to them.

---

## Repository layout

| File | Purpose |
| ---- | ------- |
| `fullinstaller.sh` | The installer and the `--doctor` diagnosis |
| `common.sh` | Shared UI, logging, helpers and the translation catalogue |
| `start` | Starts the servers and shows the live status view |
| `stop` | Stops the servers and archives the logs |
| `account_creator.sh` | Account management |

## Adding a language

All strings live in `common.sh` as one associative array per language. To add
one, copy `AK_MSG_en`, translate the values, keep every `%s` placeholder in the
same order, then add the code to `AK_LANGS` and a display name to
`AK_LANG_NAMES`. Missing keys automatically fall back to English.

---

Written by **Dulgan**.
