"""Publish the front-page image for 24 November 2026.

Reads ``entry.png`` from this repository's root, checks that it is a
complete, well-formed image of exactly 1024 x 1024 pixels and no more than
1 MiB, and then copies it atomically to ``<output>/entry.png``.

The output directory is ``MAKEFUN_OUTPUT_DIR`` when set, otherwise
``/output``.  Only the Python standard library is used and no network
access is needed.  Running the program twice always writes the same bytes,
because it copies the bundled image unchanged.
"""

import binascii
import os
import struct
import sys

MAX_BYTES = 1_048_576
WANTED_WIDTH = 1024
WANTED_HEIGHT = 1024

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"


def fail(message):
    print("error: " + message, file=sys.stderr)
    raise SystemExit(1)


def check_png(data):
    """Walk every PNG chunk, verifying lengths, CRCs and the IHDR size."""
    if len(data) < 8 + 25:
        fail("PNG file is too short to hold an IHDR chunk")
    pos = len(PNG_SIGNATURE)
    saw_ihdr = False
    saw_idat = False
    saw_iend = False
    while pos < len(data):
        if pos + 8 > len(data):
            fail("PNG chunk header is truncated")
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        body_start = pos + 8
        body_end = body_start + length
        if body_end + 4 > len(data):
            fail("PNG chunk %r is truncated" % kind.decode("latin-1"))
        stored_crc = struct.unpack(">I", data[body_end:body_end + 4])[0]
        actual_crc = binascii.crc32(kind + data[body_start:body_end]) & 0xFFFFFFFF
        if stored_crc != actual_crc:
            fail("PNG chunk %r has a bad CRC" % kind.decode("latin-1"))
        if kind == b"IHDR":
            if saw_ihdr:
                fail("PNG has more than one IHDR chunk")
            if length != 13:
                fail("PNG IHDR chunk has the wrong length")
            width, height = struct.unpack(">II", data[body_start:body_start + 8])
            if (width, height) != (WANTED_WIDTH, WANTED_HEIGHT):
                fail("PNG is %dx%d, expected 1024x1024" % (width, height))
            saw_ihdr = True
        elif kind == b"IDAT":
            saw_idat = True
        elif kind == b"IEND":
            if length != 0:
                fail("PNG IEND chunk must be empty")
            if body_end + 4 != len(data):
                fail("PNG has trailing bytes after IEND")
            saw_iend = True
            break
        pos = body_end + 4
    if not saw_ihdr:
        fail("PNG has no IHDR chunk")
    if not saw_idat:
        fail("PNG has no image data (IDAT)")
    if not saw_iend:
        fail("PNG is missing its IEND chunk")


def check_jpeg(data):
    """Walk JPEG markers, read the frame size, and require a final EOI."""
    if data[-2:] != JPEG_EOI:
        fail("JPEG does not end with the end-of-image marker")
    pos = 2
    saw_frame = False
    while pos < len(data):
        if data[pos] != 0xFF:
            fail("JPEG marker expected at offset %d" % pos)
        marker = data[pos + 1]
        pos += 2
        if marker == 0xD8:  # SOI (should not repeat, but tolerate it)
            continue
        if marker == 0xD9:  # EOI
            if pos != len(data):
                fail("JPEG has bytes after the end-of-image marker")
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue  # standalone markers carry no length
        if pos + 2 > len(data):
            fail("JPEG segment length is truncated")
        seg_len = struct.unpack(">H", data[pos:pos + 2])[0]
        if seg_len < 2 or pos + seg_len > len(data):
            fail("JPEG segment overruns the file")
        if marker in (0xC0, 0xC1, 0xC2):  # baseline / progressive frames
            if seg_len < 7:
                fail("JPEG frame segment is too short")
            height = struct.unpack(">H", data[pos + 3:pos + 5])[0]
            width = struct.unpack(">H", data[pos + 5:pos + 7])[0]
            if (width, height) != (WANTED_WIDTH, WANTED_HEIGHT):
                fail("JPEG is %dx%d, expected 1024x1024" % (width, height))
            saw_frame = True
        if marker == 0xDA:  # start of scan: entropy data runs to EOI
            if not saw_frame:
                fail("JPEG scan starts before any frame header")
            return
        pos += seg_len
    if not saw_frame:
        fail("JPEG has no frame header giving its size")


def validate(data):
    if not data:
        fail("entry.png is empty")
    if len(data) > MAX_BYTES:
        fail("entry.png is %d bytes, over the 1 MiB limit" % len(data))
    if data.startswith(PNG_SIGNATURE):
        check_png(data)
        kind = "PNG"
    elif data.startswith(JPEG_SOI):
        check_jpeg(data)
        kind = "JPEG"
    else:
        fail("entry.png is neither a PNG nor a JPEG (unknown magic bytes)")
    return kind


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    source = os.path.join(here, "entry.png")
    try:
        with open(source, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        fail("cannot read entry.png: %s" % exc)
    kind = validate(data)

    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, "entry.png")
    tmp_path = os.path.join(out_dir, ".entry.png.tmp")
    with open(tmp_path, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, target)
    print("wrote %s (%s, %dx%d, %d bytes) to %s"
          % (target, kind, WANTED_WIDTH, WANTED_HEIGHT, len(data), target))


if __name__ == "__main__":
    main()
