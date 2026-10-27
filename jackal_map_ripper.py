"""Rip complete stage background maps from your own Jackal (USA) NES ROM.

Reads the level data straight out of the ROM: no emulator, no recompile, stdlib only.
Writes one indexed PNG per stage (512 px wide, full stage height, start of the stage at the bottom).

Usage: python jackal_map_ripper.py "Jackal (USA).nes" [--stage N ...] [--out DIR]
"""
import argparse
import hashlib
import json
import pathlib
import struct
import sys
import zlib

__version__ = "1.1.0"

HERE = pathlib.Path(__file__).resolve().parent
INES_HEADER_SIZE = 16
PRG_BANK_SIZE = 0x4000
SWITCHABLE_BASE = 0x8000
FIXED_BASE = 0xC000
VRAM_SIZE = 0x4000
TILE_PIXELS = 8
TILE_BYTES = 16
PALETTE_BYTES = 32
STREAM_END = 0xFF
LITERAL_RUN_FLAG = 0x80
PPU_STRING_END = 0xFE
PALETTE_ADDRESS = 0x3F00


class Rom:
    """PRG ROM with UxROM addressing: last bank fixed at $C000, any bank at $8000."""

    def __init__(self, path, profile):
        data = pathlib.Path(path).read_bytes()
        if data[:4] != b"NES\x1a":
            sys.exit(f"{path}: not an iNES ROM")
        mapper = (data[6] >> 4) | (data[7] & 0xF0)
        prg = data[INES_HEADER_SIZE:INES_HEADER_SIZE + data[4] * PRG_BANK_SIZE]
        if mapper != profile["mapper"]:
            sys.exit(f"{path}: mapper {mapper}, expected {profile['mapper']}")
        if hashlib.sha1(prg).hexdigest() != profile["prg_sha1"]:
            print(f"warning: {path} is not a known-good {profile['name']} dump, output may be wrong", file=sys.stderr)
        self.prg = prg
        self.fixed_bank = len(prg) // PRG_BANK_SIZE - 1

    def byte(self, bank, address):
        if address >= FIXED_BASE:
            return self.prg[self.fixed_bank * PRG_BANK_SIZE + address - FIXED_BASE]
        return self.prg[bank * PRG_BANK_SIZE + address - SWITCHABLE_BASE]

    def word(self, bank, address):
        return self.byte(bank, address) | self.byte(bank, address + 1) << 8

    def stream(self, bank, address):
        while True:
            yield self.byte(bank, address)
            address += 1


def decode_rle(stream):
    """One graphics stream: [addrHi, addrLo] then runs. $FF ends; $80|n = n literal bytes; n = next byte n times.
    Returns (ppu_address, decoded bytes)."""
    address = next(stream) << 8 | next(stream)
    out = bytearray()
    for control in stream:
        if control == STREAM_END:
            break
        count = control & ~LITERAL_RUN_FLAG
        if control & LITERAL_RUN_FLAG:
            out += bytes(next(stream) for _ in range(count))
        else:
            out += bytes([next(stream)]) * count
    return address, out


def load_graphics_set(rom, profile, set_id):
    """Replays the game's graphics loader ($C3C3): a list of [bank, pointer] streams ending in $FF."""
    vram = bytearray(VRAM_SIZE)
    entry = rom.word(None, int(profile["tables"]["graphics_set_pointers"], 16) + set_id * 2)
    while (bank := rom.byte(None, entry)) != STREAM_END:
        address, data = decode_rle(rom.stream(bank, rom.word(bank, entry + 1)))
        for offset, value in enumerate(data):
            vram[(address + offset) % VRAM_SIZE] = value
        entry += 3
    return vram


def stage_palette(rom, profile, stage):
    """Stage palettes are PPU strings [$3F, $00, 32 bytes, $FE] reached through the PPU string table."""
    index = profile["palette_string_base_index"] + stage
    pointer = rom.word(None, int(profile["tables"]["ppu_string_pointers"], 16) + index * 2)
    address = rom.byte(None, pointer) << 8 | rom.byte(None, pointer + 1)
    if address != PALETTE_ADDRESS or rom.byte(None, pointer + 2 + PALETTE_BYTES) != PPU_STRING_END:
        sys.exit(f"stage {stage + 1}: palette string at {pointer:04X} has unexpected layout")
    return [rom.byte(None, pointer + 2 + i) for i in range(PALETTE_BYTES)]


class Stage:
    """Level layout: sections (512x256 px) of metatiles (32x32 px) of tiles, stored bottom-up."""

    def __init__(self, rom, profile, stage):
        tables = {name: int(address, 16) for name, address in profile["tables"].items()}
        self.rom, self.profile = rom, profile
        self.bank = rom.byte(None, tables["level_bank_by_stage"] + stage)
        self.section_list = rom.word(None, tables["section_list_pointers"] + stage * 2)
        self.section_data = rom.word(None, tables["section_data_pointers"] + stage * 2)
        self.common_metatiles = rom.word(None, tables["metatile_pointers"])
        self.stage_metatiles = rom.word(None, tables["metatile_pointers"] + stage * 2)
        self.attributes = rom.word(None, tables["metatile_attribute_pointers"] + stage * 2)
        self.threshold = rom.byte(None, tables["stage_metatile_threshold"] + stage)
        # The section data directly follows the section list, so its length is the gap between them.
        self.section_count = self.section_data - self.section_list

    def metatile_id(self, section, row, column):
        section_id = self.rom.byte(self.bank, self.section_list + section)
        address = self.section_data + section_id * self.profile["section_bytes"] \
                  + row * self.profile["section_metatile_columns"] + column
        return self.rom.byte(self.bank, address)

    def metatile_tiles(self, metatile):
        """Ids at or above the stage threshold come from the stage table, the rest from the common one ($CE1F)."""
        if metatile >= self.threshold:
            base = self.stage_metatiles + (metatile - self.threshold) * self.profile["metatile_bytes"]
        else:
            base = self.common_metatiles + metatile * self.profile["metatile_bytes"]
        return [self.rom.byte(self.bank, base + i) for i in range(self.profile["metatile_bytes"])]

    def metatile_attribute(self, metatile):
        return self.rom.byte(self.bank, self.attributes + metatile)


def render_stage(rom, profile, stage, master_palette):
    """Returns (width, height, rows of NES color indices). Row 0 is the top (end of the stage)."""
    layout = Stage(rom, profile, stage)
    vram = load_graphics_set(rom, profile, stage)
    palette = stage_palette(rom, profile, stage)
    pattern_base = profile["background_pattern_table"]
    side = profile["metatile_tiles"]
    columns = profile["section_metatile_columns"]
    rows_per_section = profile["section_metatile_rows"]
    metatile_pixels = side * TILE_PIXELS
    # The game starts every section at tile row 2 ($CD8A), so its bottom rows are never shown.
    first_row = profile["section_first_tile_row"]
    shown_rows = rows_per_section * side - first_row
    width = columns * metatile_pixels
    height = layout.section_count * shown_rows * TILE_PIXELS
    image = [bytearray(width) for _ in range(height)]

    for section in range(layout.section_count):
        for row in range(rows_per_section):
            for column in range(columns):
                metatile = layout.metatile_id(section, row, column)
                tiles = layout.metatile_tiles(metatile)
                attribute = layout.metatile_attribute(metatile)
                for tile_row in range(side):          # tile_row 0 is the bottom row of the metatile
                    section_row = row * side + tile_row
                    if section_row < first_row:
                        continue
                    # World tile row, counted up from the stage start.
                    world_row = section * shown_rows + section_row - first_row
                    quadrant_y = 0 if tile_row >= side // 2 else 1
                    for tile_column in range(side):
                        quadrant_x = tile_column // (side // 2)
                        palette_number = attribute >> (2 * (quadrant_y * 2 + quadrant_x)) & 3
                        tile = tiles[tile_row * side + tile_column]
                        pattern = pattern_base + tile * TILE_BYTES
                        y0 = height - (world_row + 1) * TILE_PIXELS
                        x0 = column * metatile_pixels + tile_column * TILE_PIXELS
                        for y in range(TILE_PIXELS):
                            low, high = vram[pattern + y], vram[pattern + y + TILE_PIXELS]
                            line = image[y0 + y]
                            for x in range(TILE_PIXELS):
                                bit = 7 - x
                                pixel = (low >> bit & 1) | (high >> bit & 1) << 1
                                color = palette[palette_number * 4 + pixel] if pixel else palette[0]
                                line[x0 + x] = color & (len(master_palette) - 1)
    return width, height, image


def write_indexed_png(path, width, height, rows, rgb_palette):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    header = struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0)   # 8-bit indexed color
    palette = b"".join(bytes.fromhex(color) for color in rgb_palette)
    pixels = zlib.compress(b"".join(b"\0" + bytes(row) for row in rows), 9)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"PLTE", palette)
                     + chunk(b"IDAT", pixels) + chunk(b"IEND", b""))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("rom", help="path to your Jackal (USA) .nes file")
    parser.add_argument("--stage", type=int, action="append", help="stage number, 1-based; repeatable (default: all)")
    parser.add_argument("--out", default="maps", help="output directory (default: maps)")
    parser.add_argument("--profile", default=str(HERE / "roms" / "jackal_usa.json"), help="ROM layout profile")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args()

    profile = json.loads(pathlib.Path(args.profile).read_text())
    master_palette = json.loads((HERE / "nes_palette.json").read_text())["rgb"]
    rom = Rom(args.rom, profile)
    stages = args.stage or range(1, profile["stage_count"] + 1)
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for number in stages:
        if not 1 <= number <= profile["stage_count"]:
            sys.exit(f"stage must be 1-{profile['stage_count']}")
        width, height, rows = render_stage(rom, profile, number - 1, master_palette)
        path = out_dir / f"stage{number}.png"
        write_indexed_png(path, width, height, rows, master_palette)
        print(f"{path}: {width}x{height}")


if __name__ == "__main__":
    main()
