#!/usr/bin/env python3
"""Remove baked-in page-number background boxes and stamp clean gold roman numerals."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

A4_W, A4_H = 2100, 2970
MARGIN_X = int(A4_W * 10 / 210)
MARGIN_Y = int(A4_H * 10 / 297)
ROM = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
       'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI']

SRC = Path('/opt/cursor/artifacts/assets')
V14 = Path('/workspace/docs/lookbook/v14-full')
OUT = Path('/opt/cursor/artifacts/assets')


def load_font(size: int = 32):
    for fp in [
        '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',
    ]:
        try:
            return ImageFont.truetype(fp, size)
        except OSError:
            continue
    return ImageFont.load_default()


def wipe_top_logos(im: Image.Image, band_h: int = 420) -> Image.Image:
    """Remove existing logo/card band from back cover top."""
    arr = np.array(im.convert('RGB'))
    h, w = arr.shape[:2]
    ref_row = arr[band_h:band_h + 3].mean(axis=0)
    for yi in range(band_h):
        fade = yi / max(band_h - 1, 1)
        arr[yi] = (ref_row * (1 - fade * 0.15) + arr[band_h + 2] * (fade * 0.15)).astype(np.uint8)
    return Image.fromarray(arr)


def wipe_br_box(im: Image.Image, box_w: int = 200, box_h: int = 150) -> Image.Image:
    """Replace bottom-right corner — removes baked numeral + background box."""
    arr = np.array(im.convert('RGB'))
    h, w = arr.shape[:2]
    x0, y0 = w - box_w, h - box_h
    ref = arr[y0 - 6:y0, x0:x0 + box_w].mean(axis=0).astype(np.uint8)
    arr[y0:y0 + box_h, x0:x0 + box_w] = ref
    return Image.fromarray(arr)


def stamp_roman(im: Image.Image, text: str) -> Image.Image:
    im = im.convert('RGBA')
    d = ImageDraw.Draw(im)
    f = load_font(32)
    bb = d.textbbox((0, 0), text, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x = im.width - tw - MARGIN_X
    y = im.height - th - MARGIN_Y
    d.text((x + 1, y + 1), text, fill=(0, 0, 0, 70), font=f)
    d.text((x, y), text, fill=(201, 162, 39, 255), font=f)
    return im.convert('RGB')


def fix_numbered_page(n: int) -> Path:
    name = f'numbered-{n:02d}.png'
    candidates = [
        SRC / f'lookbook-v14-{name}',
        V14 / name,
        SRC / f'lookbook-v13-{name}',
    ]
    src = next((p for p in candidates if p.exists()), None)
    if not src:
        raise FileNotFoundError(name)

    im = Image.open(src).convert('RGB')
    # Scale to A4 if needed
    if im.size != (A4_W, A4_H):
        s = min(A4_W / im.width, A4_H / im.height)
        nw, nh = int(im.width * s), int(im.height * s)
        im2 = im.resize((nw, nh), Image.Resampling.LANCZOS)
        canvas = Image.new('RGB', (A4_W, A4_H), im2.getpixel((2, 2)))
        canvas.paste(im2, ((A4_W - nw) // 2, (A4_H - nh) // 2))
        im = canvas

    im = wipe_br_box(im)
    im = stamp_roman(im, ROM[n])
    out = OUT / f'lookbook-v15-{name}'
    im.save(out, 'PNG', optimize=True)
    print('fixed', name, 'from', src.name)
    return out


def main():
    for n in range(1, 17):
        fix_numbered_page(n)


if __name__ == '__main__':
    main()
