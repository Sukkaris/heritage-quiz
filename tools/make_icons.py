# -*- coding: utf-8 -*-
"""ホーム画面用アイコンを生成する（使い捨て）。深緑地に「遺」の白抜き。"""
import os

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BG = (27, 58, 47)        # style.css の theme-color と同じ
FG = (238, 243, 242)
ACCENT = (75, 185, 138)
FONTS = [
    r"C:\Windows\Fonts\YuGothB.ttc",
    r"C:\Windows\Fonts\meiryob.ttc",
    r"C:\Windows\Fonts\msgothic.ttc",
]


def font_for(size):
    for path in FONTS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_icon(size, padding_ratio=0.0):
    img = Image.new("RGB", (size, size), BG)
    d = ImageDraw.Draw(img)
    # 下線のアクセント
    bar_h = max(2, size // 32)
    d.rectangle([size * 0.22, size * 0.80, size * 0.78, size * 0.80 + bar_h], fill=ACCENT)
    f = font_for(int(size * 0.56))
    text = "遺"
    box = d.textbbox((0, 0), text, font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((size - w) / 2 - box[0], (size * 0.74 - h) / 2 - box[1]), text, font=f, fill=FG)
    return img


for name, size in [("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)]:
    draw_icon(size).save(os.path.join(OUT, name))
    print("生成:", name)
