#!/usr/bin/env python3
"""Lookbook v19: adopt NOVEMBER TEN little kids logo on pages 13–14, NOVTENLK index."""
from pathlib import Path
from PIL import Image
import img2pdf
import numpy as np

A4_W, A4_H = 2100, 2970

ART = Path('/opt/cursor/artifacts/assets')
V18 = Path('/workspace/docs/lookbook/v18-full')
V19 = Path('/workspace/docs/lookbook/v19-full')
PREV = Path('/workspace/docs/lookbook/v19-previews')
OUT = V19
OUT.mkdir(parents=True, exist_ok=True)
PREV.mkdir(parents=True, exist_ok=True)

V17_PAGES = {4, 5, 6, 7, 10}
V19_PAGES = {13, 14, 16}


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
    arr = np.array(im.convert('RGB'))
    h, w = arr.shape[:2]
    bw, bh = 130, 90
    x0, y0 = w - bw - 20, h - bh - 20
    x1, y1 = x0 + bw, y0 + bh
    ref = arr[max(0, y0 - 8):y0, x0:x1].mean(axis=0).astype(np.uint8)
    for yi in range(bh):
        arr[y0 + yi, x0:x1] = ref
    return Image.fromarray(arr)


def resolve_v19(n: int) -> Path:
    names = {
        13: 'lookbook-v19-numbered-13-kids-summer.png',
        14: 'lookbook-v19-numbered-14-kids-autumn.png',
        16: 'lookbook-v19-numbered-16-index.png',
    }
    for p in [ART / names[n], V19 / f'numbered-{n:02d}.png']:
        if p.exists():
            return p
    raise FileNotFoundError(n)


def resolve_numbered(n: int) -> Path:
    if n in V19_PAGES:
        return resolve_v19(n)
    p = V18 / f'numbered-{n:02d}.png'
    if p.exists():
        return p
    raise FileNotFoundError(n)


def main():
    pages = []
    cover_src = V18 / 'cover-summer.png'
    cover = fit_a4(Image.open(cover_src))
    cover.save(OUT / 'cover-summer.png', 'PNG', optimize=True)
    pages.append(OUT / 'cover-summer.png')
    print('cover', cover_src.name)

    for n in range(1, 17):
        src = resolve_numbered(n)
        im = fit_a4(Image.open(src))
        if n not in V17_PAGES and n not in V19_PAGES:
            im = remove_small_page_number(im)
        elif n in V19_PAGES:
            im = remove_small_page_number(im)
        out = OUT / f'numbered-{n:02d}.png'
        im.save(out, 'PNG', optimize=True)
        pages.append(out)
        print('page', n, src.name)

    back_src = V18 / 'backcover-autumn.png'
    back = fit_a4(Image.open(back_src))
    back.save(OUT / 'backcover-autumn.png', 'PNG', optimize=True)
    pages.append(OUT / 'backcover-autumn.png')
    print('back', back_src.name)

    for p in pages:
        pr = Image.open(p).copy()
        pr.thumbnail((520, 740), Image.Resampling.LANCZOS)
        pr.save(PREV / f'lookbook-v19-{p.stem}-preview.jpg', 'JPEG', quality=85)

    tmp = Path('/tmp/lb19')
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
    wtmp = Path('/tmp/lb19w')
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
