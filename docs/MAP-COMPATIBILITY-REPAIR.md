Map compatibility repair — 25 October 2026, Asia/Jakarta

The client contained scene configurations from a different server layout. Sky Tower node 703 loaded S741.nif with a 512×512 world and S745 collision reference, while the running server uses the stock S701.nif layout at 448×448 for this floor. Its entrance and event coordinates were consequently outside the client's visible terrain. The main floor geometry files themselves were present and matched the original V15 archive; changing player coordinates or substituting a different NIF would have concealed the real mismatch.

Audited all 866 INI scenes supplied by the running server, plus its scene cinematics and 1,340 collision/path files. Every one of the 866 server scene files matches the CRC recorded in the matching V15 Unpacked archive. All referenced main model files are present. Of 153 distinct main models checked, 152 match that archive's CRC.

Restored 323 client data/scene files and 8 map/sknodemap files, 331 files total (about 32 MB). Incorrect geometry remaps were removed from Sky Tower floors 3, 6, 9, 14, 19 and 20. Remaining differing scene definitions, including server-defined Gaia Chronicle/book instance scenes, were restored byte-for-byte to the original server-compatible data. The repair does not rewrite the client item, enchant, shop, level, quest or text tables. No game database was modified and no server restart was performed.

Backup: private/client-original/map-compatibility-20261025T080028Z. The backup contains every replaced original file and a complete manifest. Entries with no before_sha256 were newly added. Restore replaced files from their matching relative paths and remove only those newly added files when rolling back, with the client closed.

Evidence:

- map-compatibility-manifest.json: file hashes, original ZIP CRCs and model mappings.
- map-compatibility-deployment.json: installed changes and backup location.
- map-geometry-validation.json: CRCs of all 153 distinct main model files.
- tower-floor3-assets.json: original floor-3 and floor-41 asset verification.

Limitations: S048.fsm (Snow Flame Demon Realm; also referenced by scene S695) differs from the original archive. Its scene configs already matched the server, so neither those configs nor that model were altered. A single retry to retrieve the original through the supplied MEGA link returned HTTP 509. This asset remains unverified, rather than a confirmed broken map. Optional or alternate collision/cache references absent from both source and client are listed in the audit; they were not fabricated. The partial clean-client folder remains incomplete and is not the playable client.

All restored file hashes were checked after writing. Client startup, Sky Tower 3F and a Gaia Chronicle book instance still need gameplay verification. This repair aligns the map data; it does not certify every dungeon script or quest.

Post-install verification: all 866 active client scene INIs matched the staged server originals with zero SHA256 mismatches. Restarted Game.exe and visually confirmed the server-selection screen with Ch01 (OK). Startup passes; the player still needs to verify Sky Tower 3F and a Gaia Chronicle book instance.

Player acceptance, 25 October 2026 (Asia/Jakarta): the player answered “Both work correctly” after testing Sky Tower 3F and a Gaia Chronicle book instance for terrain and spawn-position correctness. Those two gameplay checks pass. Other maps and the unverified S048 model retain the limitations above.
