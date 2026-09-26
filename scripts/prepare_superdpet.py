"""Prepare this specific reference without changing its artwork or source file.

Run: .venv/bin/python scripts/prepare_superdpet.py
Requires Pillow. The hand-traced interior protects white character regions;
outside it, white-paper unmatting retains even the faint, open pencil strokes.
"""

from hashlib import sha256
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/reference.png"
# Trace just inside the pencil contour, so edge strokes are unmatted rather
# than surrounded by opaque paper. Coordinates refer to the original image.
INTERIOR = [
    (59, 719), (123, 694), (185, 652), (241, 596), (287, 544),
    (307, 491), (323, 421), (347, 345), (380, 281), (425, 226),
    (465, 192), (507, 169), (557, 153), (596, 161), (631, 172),
    (671, 143), (724, 136), (754, 144), (788, 163), (822, 191),
    (855, 225), (889, 266), (923, 316), (952, 371), (979, 429),
    (1003, 489), (1024, 537), (1052, 577), (1093, 617),
    (1143, 655), (1194, 683), (1240, 705), (1270, 706),
    (1244, 733), (1226, 749), (1203, 751), (1196, 762),
    (1181, 750), (1169, 752), (1168, 767), (1157, 759),
    (1150, 747), (1139, 754), (1127, 746), (1119, 760),
    (1108, 746), (1098, 752), (1088, 738), (1077, 744),
    (1069, 729), (1057, 737), (1048, 722), (1038, 731),
    (1029, 713), (1020, 724), (1010, 706), (1001, 717),
    (993, 697), (984, 707), (973, 692), (965, 703),
    (951, 684), (941, 677), (930, 729), (918, 774),
    (916, 802), (923, 817), (912, 810), (902, 783),
    (899, 825), (877, 877), (865, 895), (877, 853),
    (887, 805), (853, 837), (816, 867), (773, 893),
    (737, 911), (741, 942), (753, 972), (777, 995),
    (786, 1009), (835, 1021), (880, 1034), (942, 1054),
    (983, 1078), (1027, 1113), (1057, 1157), (1080, 1209),
    (1091, 1236), (1020, 1242), (900, 1246), (750, 1248),
    (600, 1248), (450, 1243), (320, 1229), (219, 1192),
    (235, 1158), (263, 1125), (301, 1092), (344, 1065),
    (390, 1043), (438, 1025), (475, 1017), (479, 995),
    (510, 979), (539, 949), (555, 914), (562, 880),
    (526, 860), (489, 832), (460, 800), (437, 760),
    (415, 716), (401, 694), (393, 742), (394, 807),
    (406, 841), (390, 825), (373, 777), (369, 837),
    (376, 904), (394, 972), (372, 938), (358, 888),
    (351, 824), (353, 764), (323, 805), (285, 839),
    (306, 809), (327, 769), (342, 724), (345, 687),
    (331, 703), (317, 705), (310, 719), (297, 718),
    (284, 730), (272, 729), (260, 739), (246, 739),
    (232, 746), (217, 749), (201, 756), (190, 751),
    (174, 755), (163, 748), (147, 751), (135, 744),
    (124, 743), (113, 738), (101, 738), (88, 731), (76, 731),
]


def smooth_contour(points):
    """Round the traced segments without introducing polygonal mask corners."""
    result = []
    for i, p1 in enumerate(points):
        p0, p2, p3 = points[i - 1], points[(i + 1) % len(points)], points[(i + 2) % len(points)]
        for step in range(12):
            t = step / 12
            result.append(tuple(
                0.5 * (2 * p1[d] + (-p0[d] + p2[d]) * t
                       + (2 * p0[d] - 5 * p1[d] + 4 * p2[d] - p3[d]) * t**2
                       + (-p0[d] + 3 * p1[d] - 3 * p2[d] + p3[d]) * t**3)
                for d in (0, 1)
            ))
    return result


def prepare():
    original_hash = sha256(SOURCE.read_bytes()).hexdigest()
    source = Image.open(SOURCE).convert("RGB")
    if source.size != (1350, 1258):
        raise ValueError("The traced mask requires the original 1350 x 1258 reference.")
    scale = 3
    mask = Image.new("L", (source.width * scale, source.height * scale))
    ImageDraw.Draw(mask).polygon(
        [(round(x * scale), round(y * scale)) for x, y in smooth_contour(INTERIOR)], fill=255
    )
    mask = mask.resize(source.size, Image.Resampling.LANCZOS)
    pixels = []
    for (r, g, b), interior in zip(source.get_flattened_data(), mask.get_flattened_data()):
        # Solve the white-matte equation. Interior pixels remain unchanged;
        # exterior white becomes transparent, with no white in edge colors.
        ink_alpha = 255 - min(r, g, b)
        alpha = round(interior + (255 - interior) * ink_alpha / 255)
        if alpha:
            rgb = tuple(max(0, min(255, round(255 - (255 - c) * 255 / alpha)))
                        for c in (r, g, b))
            pixels.append((*rgb, alpha))
        else:
            pixels.append((0, 0, 0, 0))
    sprite = Image.new("RGBA", source.size)
    sprite.putdata(pixels)
    bounds = sprite.getbbox()
    if bounds is None:
        raise ValueError("No artwork detected; no output written.")
    sprite = sprite.crop(bounds)
    ratio = 448 / max(sprite.size)
    size = tuple(round(n * ratio) for n in sprite.size)
    # Premultiplied resizing prevents color fringes at partially clear edges.
    sprite = sprite.convert("RGBa").resize(size, Image.Resampling.LANCZOS).convert("RGBA")
    master = Image.new("RGBA", (512, 512))
    master.alpha_composite(sprite, ((512 - size[0]) // 2, (512 - size[1]) // 2))
    small = master.convert("RGBa").resize((256, 256), Image.Resampling.LANCZOS).convert("RGBA")
    assert sha256(SOURCE.read_bytes()).hexdigest() == original_hash
    for name, output in [("superdpet_idle.png", master), ("superdpet_idle_256.png", small)]:
        path = ROOT / "assets" / name
        output.save(path, optimize=True)
        print(f"{path.relative_to(ROOT)}: {output.size}, {output.mode}")
    print(f"Reference SHA-256 (unchanged): {original_hash}")


if __name__ == "__main__":
    prepare()
