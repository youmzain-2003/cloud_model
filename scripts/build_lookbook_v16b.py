#!/usr/bin/env python3
"""Lookbook v16b: remove page-number boxes via texture bootstrap; keep content; fix IV + back."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import img2pdf
import numpy as np

A4_W, A4_H = 2100, 2970
MARGIN_X = int(A4_W * 12 / 210)
MARGIN_Y = int(A4_H * 12 / 297)
ROM = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
       'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI']

ART = Path('/opt/cursor/artifacts/assets')
V15 = Path('/workspace/docs/lookbook/v15-full')
V14 = Path('/workspace/docs/lookbook/v14-full')
OUT = Path('/workspace/docs/lookbook/v16-full')
PREV = Path('/workspace/docs/lookbook/v16-previews')
OUT.mkdir(parents=True, exist_ok=True)
PREV.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(42)


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


def bootstrap_fill(arr: np.ndarray, x0: int, y0: int, x1: int, y1: int,
                   src: np.ndarray) -> None:
    """Fill region with randomly sampled pixels from src (preserves paper/photo texture)."""
    sh, sw = src.shape[:2]
    if sh < 2 or sw < 2:
        return
    bh, bw = y1 - y0, x1 - x0
    ys = rng.integers(0, sh, size=(bh, bw))
    xs = rng.integers(0, sw, size=(bh, bw))
    patch = src[ys, xs]
    # Light blur via 3x3 average to reduce speckles while keeping texture
    pad = np.pad(patch.astype(np.float32), ((1, 1), (1, 1), (0, 0)), mode='edge')
    blur = (
        pad[0:-2, 0:-2] + pad[0:-2, 1:-1] + pad[0:-2, 2:] +
        pad[1:-1, 0:-2] + pad[1:-1, 1:-1] + pad[1:-1, 2:] +
        pad[2:, 0:-2] + pad[2:, 1:-1] + pad[2:, 2:]
    ) / 9.0
    arr[y0:y1, x0:x1] = np.clip(blur, 0, 255).astype(np.uint8)

    # Feather left & top into surrounding page
    feather = 22
    for i in range(min(feather, bw)):
        a = i / feather
        left = arr[y0:y1, max(0, x0 - 1)].astype(np.float32)
        arr[y0:y1, x0 + i] = ((1 - a) * left + a * arr[y0:y1, x0 + i]).astype(np.uint8)
    for i in range(min(feather, bh)):
        a = i / feather
        top = arr[max(0, y0 - 1), x0:x1].astype(np.float32)
        arr[y0 + i, x0:x1] = ((1 - a) * top + a * arr[y0 + i, x0:x1]).astype(np.uint8)


def wipe_br(arr: np.ndarray) -> None:
    h, w = arr.shape[:2]
    # Wipe zone
    x0, y0, x1, y1 = w - 280, h - 190, w, h
    # Texture source: left of wipe (same band) + above wipe
    left = arr[y0:y1, max(0, x0 - 220):x0]
    above = arr[max(0, y0 - 220):y0, x0:x1]
    parts = [p for p in (left, above) if p.size > 100]
    if not parts:
        return
    src = np.concatenate([p.reshape(-1, 3) for p in parts], axis=0)
    # reshape to fake HxW for bootstrap
    side = int(np.sqrt(len(src))) or 1
    src = src[: side * side].reshape(side, side, 3)
    bootstrap_fill(arr, x0, y0, x1, y1, src)


def wipe_tr(arr: np.ndarray) -> None:
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = w - 220, 0, w, 160
    left = arr[y0:y1, max(0, x0 - 200):x0]
    below = arr[y1:min(h, y1 + 200), x0:x1]
    parts = [p for p in (left, below) if p.size > 100]
    if not parts:
        return
    src = np.concatenate([p.reshape(-1, 3) for p in parts], axis=0)
    side = int(np.sqrt(len(src))) or 1
    src = src[: side * side].reshape(side, side, 3)
    bootstrap_fill(arr, x0, y0, x1, y1, src)


def wipe_page_number_boxes(im: Image.Image) -> Image.Image:
    arr = np.array(im.convert('RGB'))
    wipe_br(arr)
    wipe_tr(arr)
    return Image.fromarray(arr)


def load_font(size: int = 36):
    for fp in [
        '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',
    ]:
        try:
            return ImageFont.truetype(fp, size)
        except OSError:
            continue
    return ImageFont.load_default()


def stamp_roman(im: Image.Image, text: str) -> Image.Image:
    """Gold numeral only — never a filled background rect."""
    im = im.convert('RGBA')
    overlay = Image.new('RGBA', im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    f = load_font(36)
    bb = d.textbbox((0, 0), text, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x = im.width - tw - MARGIN_X
    y = im.height - th - MARGIN_Y
    d.text((x + 1, y + 1), text, fill=(0, 0, 0, 55), font=f)
    d.text((x, y), text, fill=(201, 162, 39, 255), font=f)
    return Image.alpha_composite(im, overlay).convert('RGB')


def resolve_numbered(n: int) -> Path:
    name = f'numbered-{n:02d}.png'
    if n == 4:
        for p in [ART / 'lookbook-v16-numbered-04.png', ART / 'lookbook-v14-numbered-04.png', V14 / name]:
            if p.exists():
                return p
    # Prefer v14-full / v14 ART (pre-wipe originals with baked boxes), else v15 content
    for p in [
        V14 / name,
        ART / f'lookbook-v14-{name}',
        ART / f'lookbook-v15-{name}',
        V15 / name,
    ]:
        if p.exists():
            return p
    raise FileNotFoundError(name)


def resolve_cover() -> Path:
    for p in [ART / 'lookbook-v15-cover-summer.png', V15 / 'cover-summer.png',
              ART / 'lookbook-v14-cover-summer.png', V14 / 'cover-summer.png']:
        if p.exists():
            return p
    raise FileNotFoundError('cover')


def resolve_back() -> Path:
    for p in [ART / 'lookbook-v16-backcover-autumn.png',
              ART / 'lookbook-v15-backcover-autumn-gen.png',
              V15 / 'backcover-autumn.png']:
        if p.exists():
            return p
    raise FileNotFoundError('back')


def main():
    pages = []
    cover = fit_a4(Image.open(resolve_cover()))
    cover.save(OUT / 'cover-summer.png', 'PNG', optimize=True)
    pages.append(OUT / 'cover-summer.png')
    print('cover', resolve_cover().name)

    for n in range(1, 17):
        src = resolve_numbered(n)
        im = fit_a4(Image.open(src))
        im = wipe_page_number_boxes(im)
        im = stamp_roman(im, ROM[n])
        out = OUT / f'numbered-{n:02d}.png'
        im.save(out, 'PNG', optimize=True)
        pages.append(out)
        print('page', n, 'from', src.name)

    back = fit_a4(Image.open(resolve_back()))
    back = wipe_page_number_boxes(back)  # clear any stray corner marks
    back.save(OUT / 'backcover-autumn.png', 'PNG', optimize=True)
    pages.append(OUT / 'backcover-autumn.png')
    print('back', resolve_back().name)

    for p in pages:
        prev = Image.open(p).copy()
        prev.thumbnail((520, 740), Image.Resampling.LANCZOS)
        prev.save(PREV / f'lookbook-v16-{p.stem}-preview.jpg', 'JPEG', quality=85)

    tmp = Path('/tmp/lb-v16b'); tmp.mkdir(exist_ok=True)
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
    wtmp = Path('/tmp/lb-v16bw'); wtmp.mkdir(exist_ok=True)
    wj = []
    for i, p in enumerate(jpgs):
        im = Image.open(p); im.thumbnail((1050, 1485), Image.Resampling.LANCZOS)
        jp = wtmp / f'{i:02d}.jpg'; im.save(jp, 'JPEG', quality=72, optimize=True); wj.append(jp)
    with open(web, 'wb') as f:
        f.write(img2pdf.convert([str(j) for j in wj], layout_fun=layout))
    print('full_mb', round(full.stat().st_size / 1024 / 1024, 2))


if __name__ == '__main__':
    main()
