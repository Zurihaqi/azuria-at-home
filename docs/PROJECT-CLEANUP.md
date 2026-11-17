# Project cleanup — 29 October 2026

Removed the unused, incomplete `client/Aura Kingdom V15 Clean` rebuild, downloaded
client/server/BINS archives, downloaded music/package caches, the secondary
`staging/yokohiro` server extraction, and the generated damage-cap test binary.
The exact paths, file counts, bytes removed, and verification hashes are recorded
in `project-cleanup.json`.

Retained:

- The active `client/Requiem Aurakingdom` client and its current customizations.
- The complete VirtualBox disk/snapshot chain under `vm`. Snapshot VDIs are live
  dependencies, even though they look like backup files.
- All private credentials, database/server backups, and client rollback files.
- Bot/dashboard/operations source, runtime libraries, and development fixtures.
- The primary `staging/ultimate` server binaries, tables, and maps used by bot
  tests and protocol research; recovered original V15 tables and repair payloads.
- Download source/checksum records and the Debian ISO registered in VirtualBox.

The play/server/dashboard shortcuts are unchanged. Historical installation or
repair scripts that reference deleted downloads require those inputs to be
downloaded again. The incomplete clean-client directory no longer exists; its
historical build report is retained for reference.

This cleanup did not restart services, modify the VM, or change character data.
