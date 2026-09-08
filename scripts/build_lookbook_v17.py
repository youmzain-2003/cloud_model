#!/usr/bin/env python3
"""Lookbook v17: copy fixes, IV styling, clean back cover, NO page numbers at all."""
from pathlib import Path
from PIL import Image, ImageFilter
import img2pdf
import numpy as np

A4_W, A4_H = 2100, 2970

ART = Path('/opt/cursor/artifacts/assets')
V16 = Path('/workspace/docs/lookbook/v16-full')
OUT = Path('/workspace/docs/lookbook/v17-full')
PREV = Path('/workspace/docs/lookbook/v17-previews')
OUT.mkdir(parents=True, exist_ok=True)
PREV.mkdir(parents=True, exist_ok=True)


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


def erase_page_number(im: Image.Image) -> Image.Image:
    """Remove baked-in roman numerals / boxes from corners — never add new numbers."""
    arr = np.array(im.convert('RGB'))
    h, w = arr.shape[:2]
    blurred = np.array(im.filter(ImageFilter.GaussianBlur(16)).convert('RGB')).astype(np.float32)

    def fill(x0, y0, x1, y1):
        samples = []
        lx1, lx0 = max(0, x0 - 60), max(0, x0 - 200)
        if lx1 > lx0:
            samples.append(arr[y0:y1, lx0:lx1].reshape(-1, 3))
        ty1, ty0 = max(0, y0 - 60), max(0, y0 - 200)
        if ty1 > ty0:
            samples.append(arr[ty0:ty1, x0:x1].reshape(-1, 3))
        if not samples:
            return
        s = np.concatenate(samples, axis=0).astype(np.float32)
        mean = np.median(s, axis=0)
        std = float(s.std())
        bh, bw = y1 - y0, x1 - x0
        if mean.mean() > 175 and std < 28:
            patch = np.zeros((bh, bw, 3), dtype=np.float32)
            patch[:] = mean
        else:
            patch = blurred[y0:y1, x0:x1].copy()
            patch = 0.88 * patch + 0.12 * mean
        yy, xx = np.mgrid[0:bh, 0:bw]
        fx, fy = min(60, bw // 2), min(60, bh // 2)
        wx = np.ones(bw, dtype=np.float32)
        wy = np.ones(bh, dtype=np.float32)
        if fx > 0:
            t = np.linspace(0, np.pi / 2, fx)
            wx[:fx] = np.sin(t) ** 2
        if fy > 0:
            t = np.linspace(0, np.pi / 2, fy)
            wy[:fy] = np.sin(t) ** 2
        mask = np.outer(wy, wx)[..., None]
        orig = arr[y0:y1, x0:x1].astype(np.float32)
        arr[y0:y1, x0:x1] = (mask * patch + (1 - mask) * orig).astype(np.uint8)

    fill(w - 340, h - 230, w, h)
    fill(w - 250, 0, w, 170)
    return Image.fromarray(arr)


def resolve_numbered(n: int) -> Path:
    name = f'numbered-{n:02d}.png'
    v17_map = {
        4: ['lookbook-v17-numbered-04.png'],
        5: ['lookbook-v17-numbered-05.png'],
        6: ['lookbook-v17-numbered-06.png'],
        7: ['lookbook-v17-numbered-07-v2.png', 'lookbook-v17-numbered-07.png'],
        10: ['lookbook-v17-numbered-10.png'],
    }
    for stem in v17_map.get(n, []):
        p = ART / stem
        if p.exists():
            return p
    for p in [V16 / name, ART / f'lookbook-v16-{name}']:
        if p.exists():
            return p
    raise FileNotFoundError(name)


def resolve_cover() -> Path:
    for p in [V16 / 'cover-summer.png', ART / 'lookbook-v15-cover-summer.png']:
        if p.exists():
            return p
    raise FileNotFoundError('cover')


def resolve_back() -> Path:
    for p in [ART / 'lookbook-v17-backcover-autumn.png', V16 / 'backcover-autumn.png']:
        if p.exists():
            return p
    raise FileNotFoundError('backcover')


def main():
    pages = []
    cover = fit_a4(Image.open(resolve_cover()))
    cover.save(OUT / 'cover-summer.png', 'PNG', optimize=True)
    pages.append(OUT / 'cover-summer.png')
    print('cover')

    v17_fresh = {4, 5, 6, 7, 10}
    for n in range(1, 17):
        src = resolve_numbered(n)
        im = fit_a4(Image.open(src))
        if n not in v17_fresh:
            im = erase_page_number(im)
        out = OUT / f'numbered-{n:02d}.png'
        im.save(out, 'PNG', optimize=True)
        pages.append(out)
        print('page', n, src.name)

    back = fit_a4(Image.open(resolve_back()))
    back.save(OUT / 'backcover-autumn.png', 'PNG', optimize=True)
    pages.append(OUT / 'backcover-autumn.png')
    print('back', resolve_back().name)

    for p in pages:
        pr = Image.open(p).copy()
        pr.thumbnail((520, 740), Image.Resampling.LANCZOS)
        pr.save(PREV / f'lookbook-v17-{p.stem}-preview.jpg', 'JPEG', quality=85)

    tmp = Path('/tmp/lb17')
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
    wtmp = Path('/tmp/lb17w')
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
