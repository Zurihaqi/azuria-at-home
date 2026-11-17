The active Requiem client's main UI imageset now uses its existing `main.dds`
instead of the customized `main.png`. This restores the plain V15 player and
target cards rather than the purple illustrated replacements. The DDS matches
the original V15 archive manifest by size and CRC32; its alpha channel is kept.
The card layout, dimensions, region names, and coordinates are unchanged.

The rank-specific cards in `main10.png` already match the matching V15 release.
Their rank decorations remain part of the normal game UI. No character records,
item definitions, server files, or gameplay settings were changed.

Fully close and reopen the usual Game.exe to reload the artwork. In-game visual
confirmation is pending. Checks verified XML validity, source integrity, and card
texture bounds. The unrelated existing Coin7 coordinate error is preserved.

See `default-player-card-restore.json` for the exact backup directory and hashes.
To undo, close the game and copy that backup's `main.imageset` into the active
client's `uidata/imagesets` directory, replacing the current file. The original
custom PNG was also backed up and has not been deleted.
