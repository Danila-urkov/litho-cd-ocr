"""Generate demo/ with a template Excel report and synthetic annotated images.

Why synthetic: real SEM images belong to the employer and must never be
published. The generator mimics the annotation layout the OCR parses
("Length: XXX.XX nm" labels), so the repo is runnable without company data.

Improve the visual style freely — the only contract is:
  * file names like plate_S1_A.bmp  (group S<n>, direction A-D)
  * readable "Length: <100..450>.XX nm" labels on each image
"""
import random
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

W, H = 640, 600
VALUES = [320.0, 300.0, 280.0, 180.0]  # last one becomes L3_TOP (minimum)
# label anchor points; x order matters for direction A, y order for B/C/D
POINTS = [(530, 110), (330, 210), (130, 310), (430, 410)]


def _font():
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, 16)
        except OSError:
            continue
    return ImageFont.load_default()


def make_image(path, seed):
    rnd = random.Random(seed)
    npr = np.random.default_rng(seed)
    bg = npr.normal(70, 10, (H, W)).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(bg, mode="L").convert("RGB")
    d = ImageDraw.Draw(img)

    for x in (120, 260, 400, 540):
        w = rnd.randint(9, 16)
        top, bot = rnd.randint(30, 70), H - rnd.randint(30, 70)
        for dw, col in [(w + 6, 120), (w, 190), (w // 2, 230)]:
            d.rounded_rectangle([x - dw, top, x + dw, bot], radius=dw, fill=(col, col, col))

    font = _font()
    for (x, y), val in zip(POINTS, VALUES):
        text = f"Length: {val:.2f} nm"
        d.line([x - 45, y + 22, x + 55, y + 22], fill=(220, 30, 30), width=2)
        d.rectangle([x - 52, y - 12, x + 92, y + 12], fill=(255, 255, 255))
        d.text((x - 48, y - 9), text, fill=(0, 0, 0), font=font)
    img.save(path)


def main(out_dir=Path("demo")):
    out_dir = Path(out_dir)
    img_dir = out_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for s in (1, 2):
        for _ in "ABCD":
            rows.append({"Sample": f"S{s}", "L1 [нм]": None, "L3 [нм]": None,
                         "L5 [нм]": None, "L3_TOP [нм]": None})
    pd.DataFrame(rows).to_excel(out_dir / "results.xlsx", index=False)

    for s in (1, 2):
        for i, d in enumerate("ABCD"):
            make_image(img_dir / f"plate_S{s}_{d}.bmp", seed=s * 10 + i)
    print(f"demo data written to {out_dir}/ (8 images + results.xlsx)")


if __name__ == "__main__":
    main()
