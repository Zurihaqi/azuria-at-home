# Quest 2092: Secrets of Refining — 31 October 2026

The authored objective only says `EquipItem 30714 1 1`, but acceptance grants
materials 30702, 30703 and 30711, not the finished trophy. The former equip
driver waited for an item that had never been manufactured, returned without
progress and repeatedly failed the native READY check.

The explicit semantic override now invokes a shared ordinary combination
workflow with the two native `S_Combine` recipes:

1. Recipe 134: 30702 + 30703 -> core 30708.
2. Recipe 137: core 30708 + quest ring 30711 -> trophy 30714.
3. Equip the owned trophy through SwitchItemLocation, then require native READY
   and NPC turn-in/FINISHED confirmation.

The crafting window opens through `PlayerAction` 14, whose verified native
SimpleAction jump-table entry creates operation 39 (CCombineOp) and responds
with `EnterStrengthen(0,10)`. Crafting uses `PlayerWork` 192, with recipe ID,
two short arguments and all five native counted vectors. Material bag/slot
vectors come from native inventory tracking. Success is established by actual
owned output items, not by sending a request. Existing equipped output is
recognized on reconnect. Missing ingredients fail explicitly without grants.

An initial owned-material ItemUse probe did not open the combination window;
it consumed no materials and was replaced by the verified PlayerAction path.
Crafting grants no GM privileges, adds no items through SQL, and consumes the
normal ingredients and recipe costs through the game server.

Three crafting workflow tests and fifteen quest-engine tests passed. Awan's
native journal recorded `finished/confirmed` at Unix time 1793427162.6723855,
after both recipe outputs, equipment and READY were observed in the live log.
Arden also recorded native `finished/confirmed` at 1793427281.484177. Both bots
therefore completed the crafting tutorial without database quest edits. The
status publisher now clears the active quest on turn-in and records a separate
last-completed quest, preventing a completed quest from appearing active.
The first supported recipe set is this tutorial; this is not universal support
for arbitrary forging, random recipes or missing-material acquisition.
