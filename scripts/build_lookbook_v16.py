#!/usr/bin/env python3
"""v16d: seamless BR wipe (median paper fill / photo clone-up) + clean roman stamp."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import img2pdf
import numpy as np

A4_W, A4_H = 2100, 2970
MX, MY = int(A4_W * 14 / 210), int(A4_H * 14 / 297)
ROM = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
       'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI']

ART = Path('/opt/cursor/artifacts/assets')
V15 = Path('/workspace/docs/lookbook/v15-full')
V14 = Path('/workspace/docs/lookbook/v14-full')
OUT = Path('/workspace/docs/lookbook/v16-full')
PREV = Path('/workspace/docs/lookbook/v16-previews')
OUT.mkdir(parents=True, exist_ok=True)
PREV.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(7)


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


def feather_into(arr, x0, y0, x1, y1, fx=24, fy=24):
    for i in range(min(fx, x1 - x0)):
        a = i / fx
        left = arr[y0:y1, max(0, x0 - 1)].astype(np.float32)
        arr[y0:y1, x0 + i] = ((1 - a) * left + a * arr[y0:y1, x0 + i]).astype(np.uint8)
    for i in range(min(fy, y1 - y0)):
        a = i / fy
        top = arr[max(0, y0 - 1), x0:x1].astype(np.float32)
        arr[y0 + i, x0:x1] = ((1 - a) * top + a * arr[y0 + i, x0:x1]).astype(np.uint8)


def wipe_br(arr: np.ndarray) -> None:
    h, w = arr.shape[:2]
    bw, bh = 300, 200
    x0, y0, x1, y1 = w - bw, h - bh, w, h

    # Sample paper/scene color from a safe band ABOVE the wipe (not containing the box)
    safe = arr[max(0, y0 - 120):y0, x0:x1]
    if safe.size < 100:
        safe = arr[80:200, 200:w - 200]
    mean = np.median(safe.reshape(-1, 3), axis=0)
    std = float(np.std(safe.astype(np.float32)))

    # Dark / photo page? clone rows from above instead of flat fill
    if mean.mean() < 170 and std > 18:
        src = arr[max(0, y0 - bh - 30):y0, x0:x1]
        if src.shape[0] >= 20:
            # Repeat last rows of source downward
            rows = []
            for i in range(bh):
                rows.append(src[-(1 + (i % min(40, src.shape[0]))), :])
            patch = np.stack(rows[::-1], axis=0)  # smoother continuation
            # Actually use mirrored last portion
            chunk = src[-min(bh, src.shape[0]):]
            if chunk.shape[0] < bh:
                extra = np.flipud(chunk)[: bh - chunk.shape[0]]
                chunk = np.vstack([chunk, extra])
            else:
                chunk = chunk[-bh:]
            arr[y0:y1, x0:x1] = chunk
            feather_into(arr, x0, y0, x1, y1)
            return

    # Cream / flat page: median fill + tiny grain matching paper
    grain = rng.normal(0, max(1.5, min(4.0, std * 0.15)), size=(bh, bw, 3))
    patch = np.clip(mean + grain, 0, 255).astype(np.uint8)
    arr[y0:y1, x0:x1] = patch
    feather_into(arr, x0, y0, x1, y1)


def wipe_tr(arr: np.ndarray) -> None:
    h, w = arr.shape[:2]
    bw, bh = 240, 150
    x0, y0, x1, y1 = w - bw, 0, w, bh
    safe = arr[y1:y1 + 100, x0:x1]
    if safe.size < 100:
        safe = arr[0:bh, max(0, x0 - 200):x0]
    mean = np.median(safe.reshape(-1, 3), axis=0)
    std = float(np.std(safe.astype(np.float32)))
    if mean.mean() < 170 and std > 18:
        src = arr[y1:min(h, y1 + bh + 30), x0:x1]
        if src.shape[0] >= 20:
            chunk = src[:bh] if src.shape[0] >= bh else np.vstack([src, np.flipud(src)])[:bh]
            arr[y0:y1, x0:x1] = chunk
            return
    grain = rng.normal(0, max(1.5, min(4.0, std * 0.15)), size=(bh, bw, 3))
    arr[y0:y1, x0:x1] = np.clip(mean + grain, 0, 255).astype(np.uint8)


def wipe(im: Image.Image) -> Image.Image:
    arr = np.array(im.convert('RGB'))
    wipe_br(arr)
    wipe_tr(arr)
    return Image.fromarray(arr)


def font(sz=34):
    for fp in [
        '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',
    ]:
        try:
            return ImageFont.truetype(fp, sz)
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
    d.text((x + 1, y + 1), text, fill=(0, 0, 0, 35), font=f)
    d.text((x, y), text, fill=(196, 156, 36, 255), font=f)
    return Image.alpha_composite(im, ov).convert('RGB')


def resolve_n(n: int) -> Path:
    name = f'numbered-{n:02d}.png'
    if n == 4:
        for p in [ART / 'lookbook-v16-numbered-04.png', V15 / name, V14 / name]:
            if p.exists():
                return p
    for p in [V15 / name, ART / f'lookbook-v15-{name}', V14 / name, ART / f'lookbook-v14-{name}']:
        if p.exists():
            return p
    raise FileNotFoundError(name)


def main():
    pages = []
    cover_src = next(p for p in [ART / 'lookbook-v15-cover-summer.png', V15 / 'cover-summer.png'] if p.exists())
    fit_a4(Image.open(cover_src)).save(OUT / 'cover-summer.png', 'PNG', optimize=True)
    pages.append(OUT / 'cover-summer.png')
    print('cover', cover_src.name)

    for n in range(1, 17):
        src = resolve_n(n)
        im = stamp(wipe(fit_a4(Image.open(src))), ROM[n])
        out = OUT / f'numbered-{n:02d}.png'
        im.save(out, 'PNG', optimize=True)
        pages.append(out)
        print('page', n, src.name)

    back_src = next(p for p in [
        ART / 'lookbook-v16-backcover-autumn.png', V15 / 'backcover-autumn.png'
    ] if p.exists())
    back = wipe(fit_a4(Image.open(back_src)))
    back.save(OUT / 'backcover-autumn.png', 'PNG', optimize=True)
    pages.append(OUT / 'backcover-autumn.png')
    print('back', back_src.name)

    for p in pages:
        pr = Image.open(p).copy()
        pr.thumbnail((520, 740), Image.Resampling.LANCZOS)
        pr.save(PREV / f'lookbook-v16-{p.stem}-preview.jpg', 'JPEG', quality=85)

    tmp = Path('/tmp/lb16d'); tmp.mkdir(exist_ok=True)
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
    wtmp = Path('/tmp/lb16dw'); wtmp.mkdir(exist_ok=True)
    wj = []
    for i, p in enumerate(jpgs):
        im = Image.open(p); im.thumbnail((1050, 1485), Image.Resampling.LANCZOS)
        jp = wtmp / f'{i:02d}.jpg'; im.save(jp, 'JPEG', quality=72, optimize=True); wj.append(jp)
    with open(web, 'wb') as f:
        f.write(img2pdf.convert([str(j) for j in wj], layout_fun=layout))
    print('full_mb', round(full.stat().st_size / 1024 / 1024, 2))


if __name__ == '__main__':
    main()
