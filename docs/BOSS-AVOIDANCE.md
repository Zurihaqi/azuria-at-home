# Native boss-warning avoidance — 31 October 2026

## Current implementation

Both bots' battle driver now supports Keda's Boulder Storm warning, spell 58100.
It reads the native `ClientSpellCast` packet rather than looking at the rendered
red/purple carpet. This is the first explicit pattern profile, not universal
boss-mechanic coverage.

`bots/evasion.py` validates the 24-byte packet, caster template 41165, spell ID,
warning flag and finite unit direction. The lane starts at the observed caster
position. A conservative three-unit half-width and a buffer behind the origin
are used; these are avoidance bounds, not a claim of pixel-perfect hitbox data.
The windup is three seconds plus a quarter-second recovery margin.

On a relevant warning, `combat.engage` cancels and awaits its attack/pursuit task
before allowing a dodge. The driver selects a directly clear nearby side/back
position on the restored collision grid, uses the ordinary movement driver,
checks native position confirmation, and waits for the attack window to finish.
Only then does normal pursuit resume. Dodging counts against the encounter's
existing deadline. Map changes clear pending warnings.

No GM movement, artificial speed or progression changes are used. If no safe
position exists or movement is not confirmed in time, the failure is logged.
Unknown warning spells are logged once per profile/session so their geometry
can be investigated; the driver does not pretend to avoid them.

## Verification and limits

100 targeted tests passed on the VM, including recorded-packet decoding,
malformed/unknown warning rejection, blocked escape directions, native-position
confirmation, and cancelling attacks before starting dodge movement.

Replaying a captured Keda warning against the actual packaged S622 collision
grid selected `(23.25, 83.75)` from `(21.75, 88.25)`: 4.74 world units away,
outside the conservative warning lane, with a clear direct route.

Both bots had already completed quest 1017 before avoidance was installed.
Avoidance has not yet been verified during a fresh live Keda fight. Deployment
and successful packet/grid replay do not establish that every live dodge avoids
damage. Circles, cones, rotating/overlapping attacks, tracked-target areas and
other bosses need separately verified profiles and encounter testing.

To extend this safely, identify the actual warning packet and installed spell
definition, implement its geometry/timing, replay recorded packets and blocked
routes, then verify an ordinary character's movement and damage during combat.
