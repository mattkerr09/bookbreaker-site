"""Draw the Streakgauge mark: a gauge whose needle reads how far a streak held. Writes icon.svg and the PNG/ICO sizes."""
import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / 'streakgauge-assets'
TOP, BOTTOM = (139, 137, 255), (67, 65, 230)
CX, CY, R, NEEDLE = 32, 38, 18, 55


def point(theta, radius=R):
    return CX + radius * math.cos(math.radians(theta)), CY - radius * math.sin(math.radians(theta))


def svg() -> str:
    (ax, ay), (bx, by), (vx, vy), (nx, ny) = point(200), point(-20), point(NEEDLE), point(NEEDLE, 13)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">'
            '<defs><linearGradient id="sgTile" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8b89ff"/>'
            '<stop offset="1" stop-color="#4341e6"/></linearGradient></defs>'
            '<rect width="64" height="64" rx="14" fill="url(#sgTile)"/>'
            f'<path d="M{ax:.2f} {ay:.2f}A{R} {R} 0 1 1 {bx:.2f} {by:.2f}" fill="none" stroke="#fff" stroke-opacity=".38" '
            'stroke-width="6" stroke-linecap="round"/>'
            f'<path d="M{ax:.2f} {ay:.2f}A{R} {R} 0 0 1 {vx:.2f} {vy:.2f}" fill="none" stroke="#fff" stroke-width="6" '
            'stroke-linecap="round"/>'
            f'<path d="M{CX} {CY}L{nx:.2f} {ny:.2f}" stroke="#fff" stroke-width="4.5" stroke-linecap="round"/>'
            f'<circle cx="{CX}" cy="{CY}" r="4.5" fill="#fff"/></svg>')


def raster(size: int, rounded: bool = True) -> Image.Image:
    s = 8
    big = size * s
    k = big / 64
    tile = Image.new('RGBA', (big, big))
    pixels = tile.load()
    for y in range(big):
        for x in range(big):
            t = (x + y) / (2 * big)
            pixels[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)) + (255,)
    mask = Image.new('L', (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, big - 1, big - 1], radius=14 * k if rounded else 0, fill=255)
    image = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    image.paste(tile, (0, 0), mask)
    draw = ImageDraw.Draw(image, 'RGBA')
    # PIL grows an arc's width inward from the box, so the box sits half a stroke outside the centre line.
    box = [(CX - R - 3) * k, (CY - R - 3) * k, (CX + R + 3) * k, (CY + R + 3) * k]
    width = round(6 * k)

    def cap(theta, colour):
        x, y = point(theta)
        draw.ellipse([(x - 3) * k, (y - 3) * k, (x + 3) * k, (y + 3) * k], fill=colour)

    faint = (255, 255, 255, 97)
    overlay = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.arc(box, 160, 380, fill=faint, width=width)
    for theta in (-20,):
        x, y = point(theta)
        od.ellipse([(x - 3) * k, (y - 3) * k, (x + 3) * k, (y + 3) * k], fill=faint)
    image = Image.alpha_composite(image, overlay)
    draw = ImageDraw.Draw(image, 'RGBA')
    draw.arc(box, 160, 360 - NEEDLE, fill='white', width=width)
    cap(200, 'white')
    cap(NEEDLE, 'white')
    nx, ny = point(NEEDLE, 13)
    draw.line([CX * k, CY * k, nx * k, ny * k], fill='white', width=round(4.5 * k))
    for x, y in ((CX, CY), (nx, ny)):
        r = 2.25 if (x, y) != (CX, CY) else 4.5
        draw.ellipse([(x - r) * k, (y - r) * k, (x + r) * k, (y + r) * k], fill='white')
    return image.resize((size, size), Image.LANCZOS)


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    (OUT / 'icon.svg').write_text(svg() + '\n')
    raster(512).save(OUT / 'icon-512.png')
    raster(180, rounded=False).convert('RGB').save(OUT / 'apple-touch-icon.png')
    raster(64).save(OUT / 'favicon.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print('wrote', sorted(p.name for p in OUT.iterdir()))
