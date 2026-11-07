import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ARTIFACTS_DIR = r"C:\Users\Gabriel\.gemini\antigravity\brain\757f1990-f0f9-4d5d-a37a-2b14571485e1"
ASSETS_DIR = r"d:\HQ-Gabriel\Code\projek_kumacleaner\assets"
os.makedirs(ASSETS_DIR, exist_ok=True)

# 1. Process Robot Vacuum
robot_path = os.path.join(ARTIFACTS_DIR, "robot_vacuum_1794010347559.jpg")
robot_img = Image.open(robot_path).convert("RGBA")
robot_arr = np.array(robot_img, dtype=np.float32)

# Mask out white background
bg = np.array([255, 255, 255], dtype=np.float32)
dist = np.sqrt(np.sum((robot_arr[:, :, :3] - bg)**2, axis=2))

mask = dist > 35
y_idx, x_idx = np.where(mask)
min_y, max_y = y_idx.min(), y_idx.max()
min_x, max_x = x_idx.min(), x_idx.max()

cx = (min_x + max_x) / 2.0
cy = (min_y + max_y) / 2.0
r = max(max_x - min_x, max_y - min_y) / 2.0

# Create anti-aliased circular mask
size = int(r * 2 + 10)
crop_x0 = int(cx - r - 5)
crop_y0 = int(cy - r - 5)
crop_x1 = crop_x0 + size
crop_y1 = crop_y0 + size

cropped = robot_img.crop((crop_x0, crop_y0, crop_x1, crop_y1))

# Generate high-res circular alpha mask with supersampling
mask_img = Image.new("L", (size * 4, size * 4), 0)
draw = ImageDraw.Draw(mask_img)
margin = 5 * 4
draw.ellipse((margin, margin, size * 4 - margin, size * 4 - margin), fill=255)
mask_img = mask_img.resize((size, size), Image.Resampling.LANCZOS)

# Remove any white fringe near edge: color decontamination
cropped_arr = np.array(cropped, dtype=np.float32)
mask_arr = np.array(mask_img, dtype=np.float32) / 255.0

# Calculate alpha: combination of distance to white and circular mask
edge_dist = np.sqrt(np.sum((cropped_arr[:, :, :3] - bg)**2, axis=2))
alpha_ch = np.clip((edge_dist - 15) / 35.0, 0, 1) * mask_arr

# If alpha is semi-transparent near white edge, darken edge pixels slightly to remove white fringing
semi = (alpha_ch > 0.05) & (alpha_ch < 0.95)
cropped_arr[semi, :3] = cropped_arr[semi, :3] * 0.75

cropped_arr[:, :, 3] = alpha_ch * 255.0
final_robot = Image.fromarray(np.uint8(cropped_arr), "RGBA")

out_robot = os.path.join(ASSETS_DIR, "robot_vacuum.png")
final_robot.save(out_robot, "PNG")
print(f"Saved robot_vacuum.png: {final_robot.size}")

# 2. Process Dock Station
dock_path = os.path.join(ARTIFACTS_DIR, "dock_station_1794010368188.jpg")
dock_img = Image.open(dock_path).convert("RGBA")
dock_arr = np.array(dock_img, dtype=np.float32)

dist_dock = np.sqrt(np.sum((dock_arr[:, :, :3] - bg)**2, axis=2))
mask_dock = dist_dock > 30
dy_idx, dx_idx = np.where(mask_dock)

pad = 12
d_min_y, d_max_y = max(0, dy_idx.min() - pad), min(1024, dy_idx.max() + pad)
d_min_x, d_max_x = max(0, dx_idx.min() - pad), min(1024, dx_idx.max() + pad)

dock_cropped = dock_img.crop((d_min_x, d_min_y, d_max_x, d_max_y))
dock_crop_arr = np.array(dock_cropped, dtype=np.float32)

# Alpha from white distance
dock_dist = np.sqrt(np.sum((dock_crop_arr[:, :, :3] - bg)**2, axis=2))
dock_alpha = np.clip((dock_dist - 15) / 35.0, 0, 1)

# Remove white fringe
semi_dock = (dock_alpha > 0.05) & (dock_alpha < 0.95)
dock_crop_arr[semi_dock, :3] = dock_crop_arr[semi_dock, :3] * 0.75
dock_crop_arr[:, :, 3] = dock_alpha * 255.0

final_dock = Image.fromarray(np.uint8(dock_crop_arr), "RGBA")
out_dock = os.path.join(ASSETS_DIR, "dock_station.png")
final_dock.save(out_dock, "PNG")
print(f"Saved dock_station.png: {final_dock.size}")
