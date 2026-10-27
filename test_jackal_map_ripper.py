"""Self-check that needs no ROM. Run: python test_jackal_map_ripper.py"""
import pathlib
import tempfile

from jackal_map_ripper import decode_rle, write_indexed_png


def test_decode_rle():
    # address $1234, 3x $AA, literal [1, 2], end; bytes after the end marker must be ignored
    stream = iter([0x12, 0x34, 0x03, 0xAA, 0x82, 0x01, 0x02, 0xFF, 0x99])
    address, data = decode_rle(stream)
    assert address == 0x1234
    assert data == bytes([0xAA, 0xAA, 0xAA, 0x01, 0x02])
    assert next(stream) == 0x99


def test_png_header():
    with tempfile.TemporaryDirectory() as directory:
        path = pathlib.Path(directory) / "t.png"
        write_indexed_png(path, 2, 1, [bytearray([0, 1])], ["000000", "FFFFFF"])
        data = path.read_bytes()
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
        assert data[16:24] == (2).to_bytes(4, "big") + (1).to_bytes(4, "big")


if __name__ == "__main__":
    test_decode_rle()
    test_png_header()
    print("ok")
