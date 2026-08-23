#!/usr/bin/env python3
"""Assemble lookbook v15: integrated cover/back, clean page numbers, v14 content pages."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import img2pdf

A4_W, A4_H = 2100, 2970
MARGIN_X = int(A4_W * 10 / 210)
MARGIN_Y = int(A4_H * 10 / 297)
ROM = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
       'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI']

ART = Path('/opt/cursor/artifacts/assets')
V14 = Path('/workspace/docs/lookbook/v14-full')
OUT = Path('/workspace/docs/lookbook/v15-full')
PREV = Path('/workspace/docs/lookbook/v15-previews')
OUT.mkdir(parents=True, exist_ok=True)
PREV.mkdir(parents=True, exist_ok=True)


def resolve(name: str) -> Path:
    stem = Path(name).stem
    candidates = [
        ART / f'lookbook-v15-{stem}.png',
        ART / f'lookbook-v14-{stem}.png',
        V14 / name,
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(name)


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


def ensure_roman(im: Image.Image, text: str) -> Image.Image:
    """Only add numeral if v15 asset missing — v15 pages already have clean numerals."""
    return im


def main():
    # Prefer generated back cover with integrated logos
    back_candidates = [
        ART / 'lookbook-v15-backcover-autumn-gen.png',
        ART / 'lookbook-v15-backcover-autumn.png',
    ]
    back_src = next((p for p in back_candidates if p.exists()), resolve('backcover-autumn.png'))

    order = (
        [ART / 'lookbook-v15-cover-summer.png'] +
        [resolve(f'numbered-{i:02d}.png') for i in range(1, 17)] +
        [back_src]
    )
    finals = []
    names = (
        ['cover-summer.png'] +
        [f'numbered-{i:02d}.png' for i in range(1, 17)] +
        ['backcover-autumn.png']
    )
    for name, src in zip(names, order):
        im = fit_a4(Image.open(src))
        if name.startswith('numbered-'):
            n = int(name[9:11])
            # v15 numbered assets already have clean numerals; skip re-stamp
            if not str(src).endswith(f'lookbook-v15-numbered-{n:02d}.png'):
                im = im.convert('RGBA')
                d = ImageDraw.Draw(im)
                f = load_font(32)
                bb = d.textbbox((0, 0), ROM[n], font=f)
                tw, th = bb[2] - bb[0], bb[3] - bb[1]
                x = A4_W - tw - MARGIN_X
                y = A4_H - th - MARGIN_Y
                d.text((x + 1, y + 1), ROM[n], fill=(0, 0, 0, 70), font=f)
                d.text((x, y), ROM[n], fill=(201, 162, 39, 255), font=f)
                im = im.convert('RGB')
        out = OUT / name
        im.save(out, 'PNG', optimize=True)
        prev = im.copy()
        prev.thumbnail((520, 740), Image.Resampling.LANCZOS)
        prev.save(PREV / f'lookbook-v15-{Path(name).stem}-preview.jpg', 'JPEG', quality=85)
        finals.append(out)
        print('built', name, 'from', src.name)

    tmp = Path('/tmp/lb-v15')
    tmp.mkdir(exist_ok=True)
    jpgs = []
    for i, p in enumerate(finals):
        jp = tmp / f'{i:02d}.jpg'
        Image.open(p).convert('RGB').save(jp, 'JPEG', quality=92, optimize=True)
        jpgs.append(jp)

    full = Path('/workspace/docs/lookbook/NEKKAR-X-Lookbook-2026-Inaugural-full.pdf')
    web = Path('/workspace/docs/lookbook/NEKKAR-X-Lookbook-2026-Inaugural-web.pdf')
    layout = img2pdf.get_layout_fun((img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297)))
    with open(full, 'wb') as f:
        f.write(img2pdf.convert([str(j) for j in jpgs], layout_fun=layout))
    wtmp = Path('/tmp/lb-v15w')
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
