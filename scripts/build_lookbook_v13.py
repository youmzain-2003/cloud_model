#!/usr/bin/env python3
"""Assemble NEKKAR X inaugural lookbook v13 at A4 magazine size."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import img2pdf

# A4 portrait at ~254 DPI (brand magazine equivalent)
A4_W, A4_H = 2100, 2970
MARGIN_MM = 10  # ~1cm from corner for page numbers
MARGIN_X = int(A4_W * MARGIN_MM / 210)
MARGIN_Y = int(A4_H * MARGIN_MM / 297)

ROM = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
       'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI']

ART = Path('/opt/cursor/artifacts/assets')
V12 = Path('/workspace/docs/lookbook/v12-full')
OUT = Path('/workspace/docs/lookbook/v13-full')
PREV = Path('/workspace/docs/lookbook/v13-previews')
OUT.mkdir(parents=True, exist_ok=True)
PREV.mkdir(parents=True, exist_ok=True)


def source(name: str) -> Path:
    stem = Path(name).stem
    v13 = ART / f'lookbook-v13-{stem}.png'
    if v13.exists():
        return v13
    return V12 / name


def fit_a4(im: Image.Image, bg=(250, 247, 242)) -> Image.Image:
    im = im.convert('RGB')
    scale = min(A4_W / im.width, A4_H / im.height)
    nw, nh = int(im.width * scale), int(im.height * scale)
    im2 = im.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', (A4_W, A4_H), bg)
    canvas.paste(im2, ((A4_W - nw) // 2, (A4_H - nh) // 2))
    return canvas


def clear_page_number_artifacts(im: Image.Image) -> Image.Image:
    """Clear only bottom-right zone before stamping — avoid touching content."""
    im = im.copy()
    w, h = im.size
    d = ImageDraw.Draw(im)
    sx = max(0, w - MARGIN_X - 80)
    sy = max(0, h - MARGIN_Y - 60)
    col = im.getpixel((sx, sy))
    d.rectangle([int(w * 0.90), int(h * 0.955), w, h], fill=col)
    return im


def stamp_roman(im: Image.Image, text: str) -> Image.Image:
    im = clear_page_number_artifacts(im)
    d = ImageDraw.Draw(im)
    w, h = im.size
    try:
        f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf', 32)
    except OSError:
        f = ImageFont.load_default()
    bb = d.textbbox((0, 0), text, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x = w - tw - MARGIN_X
    y = h - th - MARGIN_Y
    # text only — no background box
    d.text((x, y), text, fill=(201, 162, 39), font=f)
    return im


def main():
    order = ['cover-summer.png'] + [f'numbered-{i:02d}.png' for i in range(1, 17)] + ['backcover-autumn.png']
    finals = []
    for name in order:
        src = source(name)
        if not src.exists():
            raise FileNotFoundError(src)

        im = fit_a4(Image.open(src))
        if name.startswith('numbered-'):
            n = int(name.split('-')[1].split('.')[0])
            im = stamp_roman(im, ROM[n])
        out = OUT / name
        im.save(out, 'PNG', optimize=True)
        prev = im.copy()
        prev.thumbnail((520, 740), Image.Resampling.LANCZOS)
        prev.save(PREV / f'lookbook-v13-{Path(name).stem}-preview.jpg', 'JPEG', quality=85)
        finals.append(out)
        print('built', name, im.size)

    tmp = Path('/tmp/lb-v13-pdf')
    tmp.mkdir(exist_ok=True)
    jpgs = []
    for i, p in enumerate(finals):
        jp = tmp / f'{i:02d}.jpg'
        Image.open(p).convert('RGB').save(jp, 'JPEG', quality=92, optimize=True)
        jpgs.append(jp)

    full = Path('/workspace/docs/lookbook/NEKKAR-X-Lookbook-2026-Inaugural-full.pdf')
    web = Path('/workspace/docs/lookbook/NEKKAR-X-Lookbook-2026-Inaugural-web.pdf')
    with open(full, 'wb') as f:
        f.write(img2pdf.convert([str(j) for j in jpgs], pagesize=img2pdf.get_layout_fun((210, 297))))

    wtmp = Path('/tmp/lb-v13-web')
    wtmp.mkdir(exist_ok=True)
    wj = []
    for i, p in enumerate(jpgs):
        im = Image.open(p)
        im.thumbnail((1050, 1485), Image.Resampling.LANCZOS)
        jp = wtmp / f'{i:02d}.jpg'
        im.save(jp, 'JPEG', quality=72, optimize=True)
        wj.append(jp)
    with open(web, 'wb') as f:
        f.write(img2pdf.convert([str(j) for j in wj], pagesize=img2pdf.get_layout_fun((210, 297))))

    print('full_mb', round(full.stat().st_size / 1024 / 1024, 2))
    print('web_mb', round(web.stat().st_size / 1024 / 1024, 2))


if __name__ == '__main__':
    main()
