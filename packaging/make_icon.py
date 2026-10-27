"""Draw the app icon (a white game pad on a navy tile) as a multi-size .ico. MIT."""
from pathlib import Path
import sys

from PIL import Image, ImageDraw

SIZES = (16, 20, 24, 32, 40, 48, 64, 256)
NAVY, WHITE = (30, 45, 80, 255), (255, 255, 255, 255)


def draw(size):
    scale = 8  # draw large, then downsample for smooth edges
    big = size * scale
    image = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    margin = max(scale, round(big * .04))  # about 4% padding, at least 1px at 16px
    pen.rounded_rectangle((margin, margin, big - margin, big - margin), round(big * .22), fill=NAVY)
    # Pad body: a wide rounded bar with two grips below it.
    cx, cy = big / 2, big * .45
    body_w, body_h = big * .72, big * .28
    left, top = cx - body_w / 2, cy - body_h / 2
    pen.rounded_rectangle((left, top, left + body_w, top + body_h), round(body_h / 2), fill=WHITE)
    # Grips hang below the body and lean outward, so the shape reads as a game pad at 16 px.
    grip_w, grip_h = big * .2, big * .3
    for x in (left + body_w * .18, left + body_w * .82):
        pen.ellipse((x - grip_w / 2, cy, x + grip_w / 2, cy + grip_h), fill=WHITE)
    # D-pad and two face buttons cut out in navy.
    dx, arm, thick = left + body_w * .27, big * .075, big * .03
    pen.rectangle((dx - arm, cy - thick, dx + arm, cy + thick), fill=NAVY)
    pen.rectangle((dx - thick, cy - arm, dx + thick, cy + arm), fill=NAVY)
    bx, r = left + body_w * .73, big * .036
    for ox, oy in ((-1, 1), (1, -1)):
        x, y = bx + ox * big * .045, cy + oy * big * .035
        pen.ellipse((x - r, y - r, x + r, y + r), fill=NAVY)
    return image.resize((size, size), Image.LANCZOS)


def main(target):
    images = [draw(size) for size in SIZES]
    images[-1].save(target, format='ICO', sizes=[(s, s) for s in SIZES], append_images=images[:-1])


if __name__ == '__main__':
    main(Path(sys.argv[1]))
