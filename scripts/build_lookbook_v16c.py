#!/usr/bin/env python3
"""v16c: exact neighbor-copy wipe for page numbers; keep v15 content; IV+back fixes."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import img2pdf
import numpy as np

A4_W, A4_H = 2100, 2970
MX = int(A4_W * 14 / 210)
MY = int(A4_H * 14 / 297)
ROM = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
       'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI']

ART = Path('/opt/cursor/artifacts/assets')
V15 = Path('/workspace/docs/lookbook/v15-full')
V14 = Path('/workspace/docs/lookbook/v14-full')
OUT = Path('/workspace/docs/lookbook/v16-full')
PREV = Path('/workspace/docs/lookbook/v16-previews')
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


def exact_wipe_br(arr: np.ndarray, bw: int = 300, bh: int = 200) -> None:
    """Overwrite BR by copying the contiguous block immediately to its left, then blend from above."""
    h, w = arr.shape[:2]
    x0, y0 = w - bw, h - bh
    # Left donor: same height, immediately left
    donor = arr[y0:h, x0 - bw:x0].copy()
    if donor.shape[1] == bw:
        arr[y0:h, x0:w] = donor
    # Vertical continuity: blend top of wipe with row above
    for i in range(min(28, bh)):
        a = i / 28.0
        above = arr[max(0, y0 - 1), x0:w].astype(np.float32)
        arr[y0 + i, x0:w] = ((1 - a) * above + a * arr[y0 + i, x0:w]).astype(np.uint8)
    # Soft left seam
    for i in range(min(20, bw)):
        a = i / 20.0
        left = arr[y0:h, x0 - 1].astype(np.float32)
        arr[y0:h, x0 + i] = ((1 - a) * left + a * arr[y0:h, x0 + i]).astype(np.uint8)


def exact_wipe_tr(arr: np.ndarray, bw: int = 240, bh: int = 160) -> None:
    h, w = arr.shape[:2]
    x0, y0 = w - bw, 0
    donor = arr[0:bh, x0 - bw:x0].copy()
    if donor.shape[1] == bw:
        arr[0:bh, x0:w] = donor
    for i in range(min(20, bw)):
        a = i / 20.0
        left = arr[0:bh, x0 - 1].astype(np.float32)
        arr[0:bh, x0 + i] = ((1 - a) * left + a * arr[0:bh, x0 + i]).astype(np.uint8)


def wipe(im: Image.Image) -> Image.Image:
    arr = np.array(im.convert('RGB'))
    # Two passes: larger then smaller, always from left donor
    exact_wipe_br(arr, 320, 220)
    exact_wipe_br(arr, 240, 160)
    exact_wipe_tr(arr, 240, 160)
    return Image.fromarray(arr)


def font(size=34):
    for fp in [
        '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',
    ]:
        try:
            return ImageFont.truetype(fp, size)
        except OSError:
            pass
    return ImageFont.load_default()


def stamp(im: Image.Image, text: str) -> Image.Image:
    im = im.convert('RGBA')
    ov = Image.new('RGBA', im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    f = font(34)
    bb = d.textbbox((0, 0), text, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x = im.width - tw - MX
    y = im.height - th - MY
    # Very soft shadow only — no filled rectangle ever
    d.text((x + 1, y + 1), text, fill=(0, 0, 0, 40), font=f)
    d.text((x, y), text, fill=(196, 156, 36, 255), font=f)
    return Image.alpha_composite(im, ov).convert('RGB')


def resolve_n(n: int) -> Path:
    name = f'numbered-{n:02d}.png'
    if n == 4:
        for p in [ART / 'lookbook-v16-numbered-04.png', V15 / name, V14 / name]:
            if p.exists():
                return p
    # Prefer v15 content (what user reviewed), fall back to v14 originals
    for p in [V15 / name, ART / f'lookbook-v15-{name}', V14 / name, ART / f'lookbook-v14-{name}']:
        if p.exists():
            return p
    raise FileNotFoundError(name)


def main():
    pages = []
    cover_src = next(p for p in [
        ART / 'lookbook-v15-cover-summer.png', V15 / 'cover-summer.png'
    ] if p.exists())
    cover = fit_a4(Image.open(cover_src))
    cover.save(OUT / 'cover-summer.png', 'PNG', optimize=True)
    pages.append(OUT / 'cover-summer.png')
    print('cover', cover_src.name)

    for n in range(1, 17):
        src = resolve_n(n)
        im = wipe(fit_a4(Image.open(src)))
        im = stamp(im, ROM[n])
        out = OUT / f'numbered-{n:02d}.png'
        im.save(out, 'PNG', optimize=True)
        pages.append(out)
        print('page', n, src.name)

    back_src = next(p for p in [
        ART / 'lookbook-v16-backcover-autumn.png', V15 / 'backcover-autumn.png'
    ] if p.exists())
    back = wipe(fit_a4(Image.open(back_src)))  # clear any corner junk only
    back.save(OUT / 'backcover-autumn.png', 'PNG', optimize=True)
    pages.append(OUT / 'backcover-autumn.png')
    print('back', back_src.name)

    for p in pages:
        pr = Image.open(p).copy()
        pr.thumbnail((520, 740), Image.Resampling.LANCZOS)
        pr.save(PREV / f'lookbook-v16-{p.stem}-preview.jpg', 'JPEG', quality=85)

    tmp = Path('/tmp/lb16c'); tmp.mkdir(exist_ok=True)
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
    wtmp = Path('/tmp/lb16cw'); wtmp.mkdir(exist_ok=True)
    wj = []
    for i, p in enumerate(jpgs):
        im = Image.open(p); im.thumbnail((1050, 1485), Image.Resampling.LANCZOS)
        jp = wtmp / f'{i:02d}.jpg'; im.save(jp, 'JPEG', quality=72, optimize=True); wj.append(jp)
    with open(web, 'wb') as f:
        f.write(img2pdf.convert([str(j) for j in wj], layout_fun=layout))
    print('full_mb', round(full.stat().st_size / 1024 / 1024, 2))


if __name__ == '__main__':
    main()
