# Quest 1020 resource classification — 31 October 2026

Quest 1020, The Unlucky Merchant, requires three Scattered Supplies (item 30302)
from actor template 40337. The native biology table classifies this actor as
class 5 (resource), with resource scene interactions 7/6 on Port Skandia.

The collection driver previously recognized only 40334, 40335 and 40336 as
resources. Every other `MonsterTreasureGot` actor went into combat. Both bots
therefore tried to damage the supply crates until the objective timed out.

## Changes

- Export all native class-5 templates from `S_Biology.ini` to the VM-local public
  `maps/resource-templates.json`, using the same source as the hostile catalog.
- Inject that catalog into each quest context, so the existing interaction
  driver handles resource objectives without individual template allowlisting.
- Preserve scene-based selection of Gather (62033) versus In Use (62034).
- Refuse attempts to send a known resource object through the generic hunting
  driver. Unknown interaction mechanics can still fail, but they no longer
  silently become prolonged melee attempts against known resources.
- Keep the actual quest failure visible when switching to fallback grinding.
- Update the normal deployment helper to regenerate the catalog on deployment.

110 targeted tests passed under the VM's Python, including native biology
classification, gathering template 40337 through skill 62033, stack-count
completion, and rejecting combat against a known resource.

Installation restarts only Awan and Arden and backs up replaced files under
`/var/backups/ak-bots/resource-classification-*`. It does not restart the game
service, grant items, or write character/quest progress into the database.

## Live verification

Deployment backup: `/var/backups/ak-bots/resource-classification-20261031T050633Z`.
Both bots collected all three supplies and completed normal NPC turn-in. Native
attempt journals recorded `finished/confirmed` for Awan at Unix time
1793423262.7107909 and Arden at 1793423274.4445527. Subsequent status showed Awan
level 12 working on quest 2092 and Arden level 11 working on quest 1022, with no
current failure. The game service and both bot units remained active.
