from PIL import Image, ImageDraw

def render_crisp_app_icon():
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = size // 2, size // 2
    r = 110

    # 1. Subtle drop shadow
    shadow_offset = 6
    for dr in range(8, 0, -1):
        alpha = int(12 * (9 - dr))
        draw.ellipse(
            (cx - r - dr, cy - r + shadow_offset - dr, cx + r + dr, cy + r + shadow_offset + dr),
            fill=(0, 0, 0, alpha)
        )

    # 2. Outer Bevel Ring (Gunmetal titanium)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(55, 58, 68, 255), outline=(75, 78, 90, 255), width=2)

    # 3. Main Chassis (Matte PBT Graphite)
    draw.ellipse((cx - r + 3, cy - r + 3, cx + r - 3, cy + r - 3), fill=(24, 25, 29, 255))

    # 4. Front Bumper Mechanical Seam
    draw.arc((cx - r + 6, cy - r + 6, cx + r - 6, cy + r - 6), start=190, end=350, fill=(14, 15, 17, 255), width=2)
    # Optical obstacle avoidance slit
    draw.rounded_rectangle((cx - 36, cy - r + 6, cx + 36, cy - r + 14), radius=4, fill=(12, 13, 16, 255))

    # 5. Dustbin Lid Outline
    draw.arc((cx - r * 0.75, cy - r * 0.75, cx + r * 0.75, cy + r * 0.75), start=20, end=160, fill=(38, 40, 48, 255), width=2)

    # 6. Central Raised LDS LiDAR Turret
    tr = 34
    # Turret shadow
    draw.ellipse((cx - tr + 2, cy - tr + 4, cx + tr + 2, cy + tr + 4), fill=(0, 0, 0, 140))
    # Brushed aluminum chamfer ring
    draw.ellipse((cx - tr, cy - tr, cx + tr, cy + tr), fill=(70, 74, 85, 255), outline=(90, 94, 108, 255), width=1)
    # Turret housing
    draw.ellipse((cx - tr + 4, cy - tr + 4, cx + tr - 4, cy + tr - 4), fill=(16, 17, 20, 255))
    # Turret top cap (dark satin acrylic)
    draw.ellipse((cx - tr + 12, cy - tr + 12, cx + tr - 12, cy + tr - 12), fill=(30, 32, 38, 255), outline=(48, 52, 62, 255), width=1)
    # Ruby laser diode pinhole
    draw.ellipse((cx - 16, cy - 2, cx - 12, cy + 2), fill=(239, 68, 68, 255))

    # 7. Status LED Pinhole (Cyan glow)
    draw.ellipse((cx - 4, cy - r + 28, cx + 4, cy - r + 36), fill=(56, 189, 248, 255))

    # Save as ICO
    img.save("assets/app_icon.ico", format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("Precision app_icon.ico rendered!")

if __name__ == '__main__':
    render_crisp_app_icon()
