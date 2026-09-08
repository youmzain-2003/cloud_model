#!/usr/bin/env python3
"""Assemble lookbook v14: A4, prefer v14 assets, NO post-hoc page-number backgrounds."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import img2pdf

A4_W, A4_H = 2100, 2970
MARGIN_X = int(A4_W * 10 / 210)  # ~1cm
MARGIN_Y = int(A4_H * 10 / 297)
ROM = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
       'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI']

ART = Path('/opt/cursor/artifacts/assets')
V13 = Path('/workspace/docs/lookbook/v13-full')
OUT = Path('/workspace/docs/lookbook/v14-full')
PREV = Path('/workspace/docs/lookbook/v14-previews')
OUT.mkdir(parents=True, exist_ok=True)
PREV.mkdir(parents=True, exist_ok=True)


def resolve(name: str) -> Path:
    stem = Path(name).stem
    for p in [ART / f'lookbook-v14-{stem}.png', ART / f'lookbook-v13-{stem}.png', V13 / name]:
        if p.exists():
            return p
    raise FileNotFoundError(name)


def fit_a4(im: Image.Image) -> Image.Image:
    im = im.convert('RGB')
    s = min(A4_W / im.width, A4_H / im.height)
    nw, nh = int(im.width * s), int(im.height * s)
    im2 = im.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', (A4_W, A4_H), im2.getpixel((2, 2)))
    canvas.paste(im2, ((A4_W - nw) // 2, (A4_H - nh) // 2))
    return canvas


def ensure_roman(im: Image.Image, text: str) -> Image.Image:
    """Draw ONLY translucent/gold text near BR corner — never paint a background box.
    Skip if a similar numeral already occupies the corner (baked-in)."""
    im = im.convert('RGBA')
    w, h = im.size
    # sample BR corner — if already gold-ish text region, still overlay clean numeral
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf', 30)
    except OSError:
        f = ImageFont.load_default()
    bb = d.textbbox((0, 0), text, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x = w - tw - MARGIN_X
    y = h - th - MARGIN_Y
    # soft shadow only (no filled rect)
    d.text((x + 1, y + 1), text, fill=(0, 0, 0, 90), font=f)
    d.text((x, y), text, fill=(201, 162, 39, 255), font=f)
    return im.convert('RGB')


def main():
    order = (['cover-summer.png'] +
             [f'numbered-{i:02d}.png' for i in range(1, 17)] +
             ['backcover-autumn.png'])
    finals = []
    for name in order:
        src = resolve(name)
        im = fit_a4(Image.open(src))
        if name.startswith('numbered-'):
            n = int(name[9:11])
            # Prefer baked numerals from generation; add clean text-only if missing
            # Always ensure a clean BR numeral WITHOUT background wipe
            im = ensure_roman(im, ROM[n])
        out = OUT / name
        im.save(out, 'PNG', optimize=True)
        prev = im.copy()
        prev.thumbnail((520, 740), Image.Resampling.LANCZOS)
        prev.save(PREV / f'lookbook-v14-{Path(name).stem}-preview.jpg', 'JPEG', quality=85)
        finals.append(out)
        print('built', name, 'from', src.name)

    tmp = Path('/tmp/lb-v14')
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
    wtmp = Path('/tmp/lb-v14w'); wtmp.mkdir(exist_ok=True)
    wj = []
    for i, p in enumerate(jpgs):
        im = Image.open(p); im.thumbnail((1050, 1485), Image.Resampling.LANCZOS)
        jp = wtmp / f'{i:02d}.jpg'; im.save(jp, 'JPEG', quality=72, optimize=True); wj.append(jp)
    with open(web, 'wb') as f:
        f.write(img2pdf.convert([str(j) for j in wj], layout_fun=layout))
    print('full_mb', round(full.stat().st_size / 1024 / 1024, 2))


if __name__ == '__main__':
    main()
