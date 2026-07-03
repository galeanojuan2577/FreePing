"""Generate the freeping.ico icon for Windows installer.

Requires: pip install Pillow (optional, fallback works without it)
Usage: python build/generate_icon.py

Creates a 256x256 icon with 'FP' text on a blue-green gradient circle,
representing ping reduction (network signal icon below).
"""

import struct
from pathlib import Path


def create_ico(output_path: str = "build/freeping.ico") -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
        has_pil = True
    except ImportError:
        has_pil = False

    output_path = Path(__file__).parent.parent / output_path

    if has_pil:
        img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        for y in range(256):
            for x in range(256):
                dx, dy = x - 128, y - 128
                dist = (dx * dx + dy * dy) ** 0.5
                if dist > 126:
                    continue
                t = dist / 126
                r = int(20 + 10 * t)
                g = int(150 - 80 * t)
                b = int(200 - 40 * t)
                img.putpixel((x, y), (r, g, b, 255))

        draw.ellipse([2, 2, 254, 254], outline=(255, 255, 255, 180), width=3)

        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 100
            )
        except OSError:
            try:
                font = ImageFont.truetype(
                    "C:\\Windows\\Fonts\\segoeuib.ttf", 100
                )
            except OSError:
                font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), "FP", font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (256 - tw) // 2 - bbox[0]
        ty = (256 - th) // 2 - bbox[1]
        draw.text((tx, ty), "FP", fill=(255, 255, 255, 255), font=font)

        for i, offset in enumerate([10, 25, 45]):
            xc = 128 + (i - 1) * 25
            yc = 210
            draw.arc(
                [xc - offset, yc - offset, xc + offset, yc + offset],
                start=180 + (i - 1) * 20,
                end=360 - (i - 1) * 20,
                fill=(255, 255, 255, 180),
                width=3,
            )

        img.save(output_path, format="ICO", sizes=[(256, 256)])
        print(f"OK: Icon created {output_path} (256x256, Pillow)")
    else:
        _create_ico_fallback(output_path)


def _create_ico_fallback(output_path: Path) -> None:
    with open(output_path, "wb") as f:
        f.write(b"\x00\x00")
        f.write(struct.pack("<H", 1))
        f.write(struct.pack("<H", 1))
        png_data = _create_minimal_png(32)
        f.write(struct.pack("<I", 32))
        f.write(struct.pack("<I", 32))
        f.write(struct.pack("<H", 0))
        f.write(struct.pack("<H", 32))
        f.write(struct.pack("<I", len(png_data)))
        f.write(struct.pack("<I", 22))
        f.write(png_data)
    print(f"OK: Icon created {output_path} (32x32, fallback)")


def _create_minimal_png(size: int, r: int = 30, g: int = 140, b: int = 180) -> bytes:
    import zlib

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(
        b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    )

    raw = b""
    for y in range(size):
        raw += b"\x00"
        for x in range(size):
            cx, cy = x - size // 2, y - size // 2
            dist = (cx * cx + cy * cy) ** 0.5
            max_r = size // 2 - 1
            if dist > max_r:
                raw += struct.pack("BBBB", 0, 0, 0, 0)
            else:
                t = dist / max_r
                rr = int(r + 60 * t)
                gg = int(g - 40 * t)
                bb = int(b - 20 * t)
                raw += struct.pack("BBBB", rr, gg, bb, 255)

    idat = _chunk(b"IDAT", zlib.compress(raw))
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


if __name__ == "__main__":
    create_ico()
