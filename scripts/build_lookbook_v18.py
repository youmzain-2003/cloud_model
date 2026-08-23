#!/usr/bin/env python3
"""Lookbook v18: mirror cover/back, v17 updated pages, v14 clean sources (no corner blur)."""
from pathlib import Path
from PIL import Image
import img2pdf
import numpy as np

A4_W, A4_H = 2100, 2970

ART = Path('/opt/cursor/artifacts/assets')
V17 = Path('/workspace/docs/lookbook/v17-full')
V14 = Path('/workspace/docs/lookbook/v14-full')
OUT = Path('/workspace/docs/lookbook/v18-full')
PREV = Path('/workspace/docs/lookbook/v18-previews')
OUT.mkdir(parents=True, exist_ok=True)
PREV.mkdir(parents=True, exist_ok=True)

# Pages regenerated in v17 (keep as-is — no corner processing)
V17_PAGES = {4, 5, 6, 7, 10}


def fit_a4(im: Image.Image) -> Image.Image:
    im = im.convert('RGB')
    if im.size == (A4_W, A4_H):
        return im
    s = min(A4_W / im.width, A4_H / im.height)
    nw, nh = int(im.width * s), int(im.height * s)
    im2 = im.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', (A4_W, A4_H), im2.getpixel((2, 2)))
    canvas.paste(im2, ((A4_W - nw) // 2, (A4_H - nh) // 2))
    return canvas


def remove_small_page_number(im: Image.Image) -> Image.Image:
    """Remove only a tight BR numeral patch — never blur entire corners."""
    arr = np.array(im.convert('RGB'))
    h, w = arr.shape[:2]
    bw, bh = 130, 90
    x0, y0 = w - bw - 20, h - bh - 20
    x1, y1 = x0 + bw, y0 + bh
    # Sample strip immediately above the numeral box
    ref = arr[max(0, y0 - 8):y0, x0:x1].mean(axis=0).astype(np.uint8)
    for yi in range(bh):
        arr[y0 + yi, x0:x1] = ref
    return Image.fromarray(arr)


def resolve_numbered(n: int) -> Path:
    name = f'numbered-{n:02d}.png'
    if n in V17_PAGES:
        for p in [V17 / name, ART / f'lookbook-v17-numbered-{n:02d}.png',
                  ART / f'lookbook-v17-numbered-{n:02d}-v2.png']:
            if p.exists():
                return p
    # Unmodified pages: prefer v14-full (no corner blur from v16/v17 erase)
    for p in [V14 / name, ART / f'lookbook-v14-{name}', ART / f'lookbook-v13-{name}']:
        if p.exists():
            return p
    return V17 / name


def main():
    pages = []
    cover_src = next(p for p in [
        ART / 'lookbook-v18-cover-summer.png',
        V17 / 'cover-summer.png',
    ] if p.exists())
    cover = fit_a4(Image.open(cover_src))
    cover.save(OUT / 'cover-summer.png', 'PNG', optimize=True)
    pages.append(OUT / 'cover-summer.png')
    print('cover', cover_src.name)

    for n in range(1, 17):
        src = resolve_numbered(n)
        if not src.exists():
            raise FileNotFoundError(n)
        im = fit_a4(Image.open(src))
        if n not in V17_PAGES:
            im = remove_small_page_number(im)
        out = OUT / f'numbered-{n:02d}.png'
        im.save(out, 'PNG', optimize=True)
        pages.append(out)
        print('page', n, src.name)

    back_src = next(p for p in [
        ART / 'lookbook-v18-backcover-autumn.png',
        ART / 'lookbook-v17-backcover-autumn.png',
    ] if p.exists())
    back = fit_a4(Image.open(back_src))
    back.save(OUT / 'backcover-autumn.png', 'PNG', optimize=True)
    pages.append(OUT / 'backcover-autumn.png')
    print('back', back_src.name)

    for p in pages:
        pr = Image.open(p).copy()
        pr.thumbnail((520, 740), Image.Resampling.LANCZOS)
        pr.save(PREV / f'lookbook-v18-{p.stem}-preview.jpg', 'JPEG', quality=85)

    tmp = Path('/tmp/lb18')
    tmp.mkdir(exist_ok=True)
    jpgs = []
    for i, p in enumerate(pages):
        jp = tmp / f'{i:02d}.jpg'
        Image.open(p).convert('RGB').save(jp, 'JPEG', quality=92, optimize=True)
        jpgs.append(jp)

    full = Path('/workspace/docs/lookbook/NEKKAR-X-Lookbook-2026-Inaugural-full.pdf')
    web = Path('/workspace/docs/lookbook/NEKKAR-X-Lookbook-2026-Inaugural-web.pdf')
    layout = img2pdf.get_layout_fun((img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297)))
    with open(full, 'wb') as f:
        f.write(img2pdf.convert([str(j) for j in jpgs], layout_fun=layout))
    wtmp = Path('/tmp/lb18w')
    wtmp.mkdir(exist_ok=True)
    wj = []
    for i, p in enumerate(jpgs):
        im = Image.open(p)
        im.thumbnail((1050, 1485), Image.Resampling.LANCZOS)
        jp = wtmp / f'{i:02d}.jpg'
        im.save(jp, 'JPEG', quality=72, optimize=True)
        wj.append(jp)
    with open(web, 'wb') as f:
        f.write(img2pdf.convert([str(j) for j in wj], layout_fun=layout))
    print('full_mb', round(full.stat().st_size / 1024 / 1024, 2))


if __name__ == '__main__':
    main()
