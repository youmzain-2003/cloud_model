#!/usr/bin/env python3
"""Lookbook v20: soft-gaze cover/back, all pages rebuilt without page numbers or corner marks."""
from pathlib import Path
from PIL import Image
import img2pdf

A4_W, A4_H = 2100, 2970

ART = Path('/opt/cursor/artifacts/assets')
OUT = Path('/workspace/docs/lookbook/v20-full')
PREV = Path('/workspace/docs/lookbook/v20-previews')
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


def resolve(name: str) -> Path:
    for p in [ART / name, OUT / name.replace('lookbook-v20-', '')]:
        if p.exists():
            return p
    raise FileNotFoundError(name)


def main():
    pages = []
    for stem, out_name in [
        ('lookbook-v20-cover-summer.png', 'cover-summer.png'),
        ('lookbook-v20-numbered-01.png', 'numbered-01.png'),
        ('lookbook-v20-numbered-02.png', 'numbered-02.png'),
        ('lookbook-v20-numbered-03.png', 'numbered-03.png'),
        ('lookbook-v20-numbered-04.png', 'numbered-04.png'),
        ('lookbook-v20-numbered-05.png', 'numbered-05.png'),
        ('lookbook-v20-numbered-06.png', 'numbered-06.png'),
        ('lookbook-v20-numbered-07.png', 'numbered-07.png'),
        ('lookbook-v20-numbered-08.png', 'numbered-08.png'),
        ('lookbook-v20-numbered-09.png', 'numbered-09.png'),
        ('lookbook-v20-numbered-10.png', 'numbered-10.png'),
        ('lookbook-v20-numbered-11.png', 'numbered-11.png'),
        ('lookbook-v20-numbered-12.png', 'numbered-12.png'),
        ('lookbook-v20-numbered-13.png', 'numbered-13.png'),
        ('lookbook-v20-numbered-14.png', 'numbered-14.png'),
        ('lookbook-v20-numbered-15.png', 'numbered-15.png'),
        ('lookbook-v20-numbered-16.png', 'numbered-16.png'),
        ('lookbook-v20-backcover-autumn.png', 'backcover-autumn.png'),
    ]:
        src = resolve(stem)
        im = fit_a4(Image.open(src))
        out = OUT / out_name
        im.save(out, 'PNG', optimize=True)
        pages.append(out)
        print(out_name, '<-', src.name)

    for p in pages:
        pr = Image.open(p).copy()
        pr.thumbnail((520, 740), Image.Resampling.LANCZOS)
        pr.save(PREV / f'lookbook-v20-{p.stem}-preview.jpg', 'JPEG', quality=85)

    tmp = Path('/tmp/lb20')
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
    wtmp = Path('/tmp/lb20w')
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
