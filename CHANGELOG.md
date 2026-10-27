# Changelog

## 1.1.0 — 2026-10-26
- Fix: each section is 240 px on screen, not 256. The game starts every section at tile row 2, so the bottom 2 tile rows are hidden data. Earlier maps had a 16 px seam at every section boundary and were too tall.

## 1.0.0 — 2026-10-26
- First release: rips all 6 stages of Jackal (USA) to indexed PNG straight from the ROM.
- ROM layout kept in a JSON profile (`roms/jackal_usa.json`). NES palette in `nes_palette.json`.
- Self-check `test_jackal_map_ripper.py` (RLE decoder, PNG writer), needs no ROM.
