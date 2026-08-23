#!/usr/bin/env python3
"""Integrate transparent final logos into back cover photo — no card backgrounds."""
from pathlib import Path
from PIL import Image

BASE = Path('/opt/cursor/artifacts/assets/lookbook-v14-backcover-autumn.png')
LOGO = Path('/workspace/docs/lookbook/logos-final')
OUT = Path('/opt/cursor/artifacts/assets/lookbook-v15-backcover-autumn.png')

A4_W, A4_H = 2100, 2970


def wipe_top_logos(im: Image.Image, band_h: int = 420) -> Image.Image:
    """Remove existing logo/card band from back cover top."""
    import numpy as np
    arr = np.array(im.convert('RGB'))
    h, w = arr.shape[:2]
    ref_row = arr[band_h:band_h + 3].mean(axis=0)
    for yi in range(band_h):
        fade = yi / max(band_h - 1, 1)
        arr[yi] = (ref_row * (1 - fade * 0.15) + arr[band_h + 2] * (fade * 0.15)).astype(np.uint8)
    return Image.fromarray(arr)


def fit_a4(im: Image.Image) -> Image.Image:
    im = im.convert('RGB')
    s = min(A4_W / im.width, A4_H / im.height)
    nw, nh = int(im.width * s), int(im.height * s)
    im2 = im.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', (A4_W, A4_H), im2.getpixel((2, 2)))
    canvas.paste(im2, ((A4_W - nw) // 2, (A4_H - nh) // 2))
    return canvas


def paste_logo(base: Image.Image, logo_path: Path, cx: int, cy: int, max_w: int) -> None:
    logo = Image.open(logo_path).convert('RGBA')
    ratio = max_w / logo.width
    nh = int(logo.height * ratio)
    logo = logo.resize((max_w, nh), Image.Resampling.LANCZOS)
    x = cx - max_w // 2
    y = cy
    base.paste(logo, (x, y), logo)


def main():
    base = fit_a4(Image.open(BASE)).convert('RGBA')
    # Remove v14 card logos first, then place transparent final logos once
    base_rgb = wipe_top_logos(base.convert('RGB')).convert('RGBA')
    paste_logo(base_rgb, LOGO / 'logo-nekkar-with-reading-final-transparent.png', 520, 90, 460)
    paste_logo(base_rgb, LOGO / 'logo-nekkar-x-with-reading-final-transparent.png', 1050, 70, 500)
    paste_logo(base_rgb, LOGO / 'logo-november-ten-with-reading-final-transparent.png', 1580, 90, 480)
    base_rgb.convert('RGB').save(OUT, 'PNG', optimize=True)
    print('saved', OUT)


if __name__ == '__main__':
    main()
