# V15 GM command reference — extracted, not gameplay-tested

Source: downloaded Yokohiro hxsy.rar, hxsy/ZoneServer/GMCmd.ini.
The following signatures are present in this build. The chat prefix, argument meanings, and effects still require in-game validation; do not assume that a listed command is safe or functional.

| Purpose inferred from name | Exact signature |
| --- | --- |
| Status/version | `status`, `version` |
| Item creation | `clone_item <number>` |
| Multiple items | `clone_items <number> <number>` |
| Monster spawning | `clone_monster <number> <number> <number>` |
| Level | `set_level <number>` |
| Experience | `gain_exp <number>` |
| Gold | `gain_gold <number>` |
| Coordinates | `goto <number> <number>` |
| Map transfer | `transport_node <number>`; Navea: `/transport_node 1` |
| Player teleport | `transport_to_character <word>` |
| Quest administration | `quest <rest_input>` |
| Restore | `restore` |

Use disposable test characters and back up first. Confirm normal players cannot invoke privileged operations. Item and NPC IDs must come from the matching S_Item.ini and S_Biology.ini, not a current retail database. Preserve the full GMCmd.ini alongside this reference after deployment.

Correction: `transfer <number>` targets a character identifier, not a map; it returned “no this character in this server” for argument 1. Use `transport_node` for maps. T_Node confirms node 1 is Navea, and the native TC_TransportNode handler was inspected.

Sky raid controls, inspected 25 October 2026: the actual V15 argument order for `/sky_tower_open_state` is `<action_mode> <group_id> <state_or_parameter>`. Native mode 0 dispatches SkyTowerOpenState and GMChangeOpenState(group_id,state); mode 1 updates raid info, mode 2 resets floors, mode 3 sends the raid UI packet, mode 4 changes the level limit, mode 5 clears player raid references. Do not use the argument labels from unrelated GM guides.

The live first public scene-1 group is 10400 (GroupTypes=10000, GetTowerScene divides by 10000); subsequent public groups are 10401/10402. The corresponding guild group is 10500. The Sky Realm entry-open command to test is `/sky_tower_open_state 0 10400 5`. Native PlayerCheckRegister allows states 4–8; PlayerCheckEnter allows states 5–8. State 4 therefore permits registration alone, while state 5 passes both gates. The command has not been executed or gameplay tested. Do not claim raid completion or scheduling has been tested.

Command reception confirmed later the same day: ZoneServer logged `Change SkyTower State ID[10400] Type[0] State[5]`, and MissionServer logged `SkyTowerGroup[10400] OpenState Change [3]->[5]`. The player received no visible popup. This command changes the event state; it does not teleport the character or automatically show the raid window. The client radar layout defines the separate `Root/RadarUI/Radar/BG/SkyTowerBtn` control (small gray tower icon below the minimap, beside the blossom icon). Open/reopen that interface to register and enter. Registration, qualification and actual instance entry are still untested.

Further inspection: Zrymund joined Sky Tower room 51, group 402, at 14:03:35 server log time. The live group remained state 4 (registration), while PlayerCheckEnter permits only states 5–8. `/sky_tower_open_state 0 402 5` was therefore supplied for this specific registered group; entry still awaits player confirmation. Do not confuse the public Sky Tower group 402 with the Sky Realm group 10400. The client requirement string 6083 says Sky Realm qualification normally requires a Sky Tower 20F clear on Saturday or Sunday. The unverified `sky_tower_qualify_level` parameter is not documented as a floor number: the native handler includes a bitwise mask operation, so do not recommend argument 20 as a bypass without inspecting its database function.

Later membership change explains the failed 402 test: at 14:19:49 Zrymund created and joined guild room 1001, group 502. The 14:23:54 command changed the older public group 402 from state 4 to 5; guild group 502 was still state 4. Supplied `/sky_tower_open_state 0 502 5` for existing guild team 1001 and instructed the player to select Sky Tower → Guild Raid without creating a replacement team. Entry confirmation is still pending. Before every further command, re-check the latest membership; the player is actively creating raids and changing maps during diagnostics.

Player subsequently confirmed “Entered successfully” after `/sky_tower_open_state 0 502 5` for guild room 1001. Server logs also show entry and progression through floors 1 and 2. The later floor-3 skybox issue was traced to the client's remapped scene config and handled separately; see MAP-COMPATIBILITY-REPAIR.md.
