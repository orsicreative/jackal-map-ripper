# Jackal Map Ripper

Extracts the complete background map of every stage of **Jackal** (Konami, NES, USA release) straight from your own ROM file, as PNG images.

- Reads the level data the way the game does. No emulator, no playing through the levels, no screenshots stitched together.
- Pure Python 3.8+, standard library only. Nothing to install.
- Covers all 6 stages in a few seconds. Each map is 512 px wide (the full playfield, both nametables) and covers the stage's full height, start at the bottom.

**No ROM or game graphics are included.** You need your own dump of *Jackal (USA)*. The tool warns if the dump doesn't match the known-good one (PRG SHA-1 `813e6a8b…`). The maps it produces come from Konami's game, so keep them for personal use and don't redistribute them.

## Usage

```
python jackal_map_ripper.py "Jackal (USA).nes"                 # all stages -> maps/stage1.png ... stage6.png
python jackal_map_ripper.py "Jackal (USA).nes" --stage 3       # one stage
python jackal_map_ripper.py "Jackal (USA).nes" --out D:\rips   # other output folder
python test_jackal_map_ripper.py                                # self-check, needs no ROM
```

Output PNGs are 8-bit indexed. Each pixel's index is its NES master-palette color, so you can recolor them or map them back to NES colors exactly. Swap `nes_palette.json` to use a different palette.

## How it works

Jackal (mapper 2 / UxROM, CHR-RAM) builds its scrolling background from a three-level hierarchy. All the addresses are in [`roms/jackal_usa.json`](roms/jackal_usa.json).

| Level | Size | Where |
|-------|------|-------|
| Stage | list of section ids, bottom to top | pointer table `$CFF4` (by stage), in the bank from `$DBEE` |
| Section | 8 rows × 16 metatile ids = 512×256 px | pointer table `$D000`, 128 bytes per section |
| Metatile | 4×4 tiles = 32×32 px, rows stored bottom-up | common table `($D00C)`. Ids ≥ `$CFEE[stage]` use the stage table `($D00C + stage*2)` |
| Attributes | one byte per metatile, 2 bits per 16×16 quadrant | pointer table `$D018` |

- **Graphics:** CHR-RAM is filled by the loader at `$C3C3` from graphics set *n* = stage index. The set list (`$C473`) is a series of `[bank, pointer]` entries ending in `$FF`. Each stream is a PPU address followed by RLE runs: `$FF` ends, `$80|n` copies n literal bytes, `n` repeats the next byte n times.
- **Palette:** a PPU string `[$3F, $00, 32 bytes, $FE]`, entry `$0D + stage` in the pointer table at `$D25D`.
- **Stage length:** the section data immediately follows the section list, so the number of sections is the gap between the two pointers.

The format was found by statically recompiling the game to C and tracing which code writes the game's VRAM update queue at `$0770`. The row producer lives at `$CDC7-$CFA8`. Stage 1 output was verified against live hardware state: every nametable row and every attribute quadrant matched.

## Known limitations

- Background only. Enemies, turrets and other objects that the game spawns as sprites aren't drawn.
- Static map. Destroyed buildings, opened gates and animated water show their initial ROM state.
- Some stages have filler or a repeated section above the boss area. That's what the ROM contains, not a decoding bug.
- Only verified for the USA release. Other releases (*Top Gunner*, *Final Command: Akai Yousai*) probably use different addresses. Add a profile in `roms/` and pass `--profile`.

## License

MIT for the code in this repository. See [LICENSE](LICENSE). *Jackal* is a trademark of Konami. This project isn't affiliated with or endorsed by Konami.
