#!/usr/bin/env python3
"""Create transparent PNG for NOVEMBER TEN little kids logo from white-bg version."""
from pathlib import Path
import numpy as np
from PIL import Image

SRC = Path('/workspace/docs/lookbook/logo-november-ten-little-kids-alt-white.png')
OUT = Path('/workspace/docs/lookbook/logos-final/logo-november-ten-little-kids-transparent.png')


def main():
    im = Image.open(SRC).convert('RGBA')
    arr = np.array(im)
    rgb = arr[:, :, :3].astype(np.int16)
    # Treat near-white pixels as transparent
    white = (rgb[:, :, 0] > 235) & (rgb[:, :, 1] > 235) & (rgb[:, :, 2] > 235)
    arr[white, 3] = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(OUT, 'PNG', optimize=True)
    print('saved', OUT)


if __name__ == '__main__':
    main()
