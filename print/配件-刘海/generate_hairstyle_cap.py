#!/usr/bin/env python3
"""Create a fitted centre-part hairstyle from Microduck's fixed upper head shell.

Source meshes use metres; the printable output and all parameters use millimetres.
The cap is a hollow sculpted overlay. Its front edge clears the eye and face,
and its lower side edge stays above the moving jaw and hinge region.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import distance_transform_edt, gaussian_filter
from skimage.measure import marching_cubes

HERE = Path(__file__).resolve().parent
PARTS = HERE.parent / "打印件"
UPPER_STL = PARTS / "top_head_shell_头部上壳.stl"
LOWER_STL = PARTS / "jaw_下巴.stl"
FACE_STL = PARTS / "face_part_面部零件.stl"
EYE_STL = PARTS / "noenoeil_眼睛.stl"
SOFT_MOUTH_TOP_STL = PARTS / "soft_mouth_top_软嘴顶部.stl"
SOFT_JAW_STL = PARTS / "jaw_soft_软下巴.stl"
BOTTOM_SHELL_STL = PARTS / "bottom_head_shell_头部下壳.stl"
MOTOR_SUPPORT_STL = PARTS / "motor_support_电机支架.stl"
OUT_STL = HERE / "中分发型帽.stl"
OUT_PREVIEW = HERE / "中分发型帽-preview.png"
OUT_ANGLE = HERE / "中分发型帽-斜视图.png"

# Adjust these dimensions for the actual printed head and material.
GRID_PITCH = 0.7
INNER_CLEARANCE = 1.5
BASE_HAIR_DEPTH = 5.0
MIN_EDGE_Z = 22.0


def load_stl_mm(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load_mesh(path, process=False)
    mesh.apply_scale(1000.0)
    return mesh

def make_hull_cover() -> trimesh.Trimesh:
    """A fitted cover over the original arch, with integrated parted panels."""
    pitch = GRID_PITCH
    grid_x = np.arange(-58.0, 58.01, pitch, dtype=np.float32)
    grid_y = np.arange(-81.0, 70.01, pitch, dtype=np.float32)
    grid_z = np.arange(19.0, 65.01, pitch, dtype=np.float32)
    origin = np.array((grid_x[0], grid_y[0], grid_z[0]))
    shape = (len(grid_x), len(grid_y), len(grid_z))
    arch = load_stl_mm(UPPER_STL).convex_hull
    voxels = arch.voxelized(pitch).fill()
    occupied = np.zeros(shape, dtype=bool)
    indexes = np.rint((voxels.points - origin) / pitch).astype(int)
    inside = np.all((indexes >= 0) & (indexes < np.array(shape)), axis=1)
    indexes = indexes[inside]
    occupied[indexes[:, 0], indexes[:, 1], indexes[:, 2]] = True
    arch_distance = (distance_transform_edt(~occupied) -
                     distance_transform_edt(occupied)) * pitch
    arch_distance = gaussian_filter(arch_distance.astype(np.float32), sigma=3.0)
    x = grid_x[:, None, None]
    y = grid_y[None, :, None]
    z = grid_z[None, None, :]
    cy = -8.0 - 0.7 * (z - 22.0)
    theta = np.arctan2(y - cy, x)
    front = theta + math.pi / 2
    lower = MIN_EDGE_Z + 26.0 * np.exp(-(front / 0.45) ** 2) + \
        6.0 * np.exp(-(front / 0.7) ** 2) - \
        8.0 * np.exp(-((front - 0.55) / 0.23) ** 2) - \
        8.0 * np.exp(-((front + 0.55) / 0.23) ** 2) + \
        5.0 * np.exp(-((np.abs(front) - 1.55) / 0.78) ** 2)
    lower = np.maximum(MIN_EDGE_Z, lower)
    panel_angle = np.abs(front)
    panels = np.clip((panel_angle - 0.06) / 0.15, 0.0, 1.0) * \
        np.clip((0.94 - panel_angle) / 0.19, 0.0, 1.0)
    height = (0.6 + 0.4 * np.clip((z - 22.0) / 12.0, 0.0, 1.0)) * \
        np.clip((61.0 - z) / 11.0, 0.0, 1.0)
    part = np.exp(-(front / 0.12) ** 2)
    groove_angle = 0.91 + 0.22 * np.clip((z - 25.0) / 25.0, 0.0, 1.0)
    grooves = np.maximum(
        np.exp(-((front - groove_angle) / 0.075) ** 2),
        np.exp(-((front + groove_angle) / 0.075) ** 2),
    )
    rear_groove_angle = 1.85 + 0.12 * np.clip((z - 25.0) / 25.0, 0.0, 1.0)
    rear_grooves = np.maximum(
        np.exp(-((front - rear_groove_angle) / 0.095) ** 2),
        np.exp(-((front + rear_groove_angle) / 0.095) ** 2),
    )
    side_panels = np.exp(-((panel_angle - 1.43) / 0.33) ** 2) + \
        0.9 * np.exp(-((panel_angle - 2.30) / 0.35) ** 2)
    side_panel_height = np.clip((z - 22.0) / 11.0, 0.0, 1.0) * \
        np.clip((61.0 - z) / 10.0, 0.0, 1.0)
    groove_height = np.clip((z - 25.0) / 7.0, 0.0, 1.0) * \
        np.clip((60.0 - z) / 9.0, 0.0, 1.0)
    outer_distance = BASE_HAIR_DEPTH + 7.0 * panels * height + \
        3.5 * side_panels * side_panel_height - 3.5 * part * height - \
        (2.4 * grooves + 2.0 * rear_grooves) * groove_height - arch_distance
    inner_distance = INNER_CLEARANCE - arch_distance
    field = np.minimum(np.minimum(outer_distance, z - lower), -inner_distance)
    # The parting is a real gap in the front crown, joined at the back.
    slot_width = 3.2 * np.clip((-y - 20.0) / 25.0, 0.0, 1.0)
    parting_slot = np.maximum(np.maximum(np.abs(x) - slot_width, y + 20.0), 37.0 - z)
    field = np.minimum(field, parting_slot)
    field = gaussian_filter(field.astype(np.float32), sigma=1.15)
    vertices, faces, _, _ = marching_cubes(field, level=0.0,
                                            spacing=(pitch, pitch, pitch))
    vertices += origin
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    trimesh.repair.fix_normals(mesh)
    bodies = sorted(mesh.split(), key=lambda part: abs(part.volume), reverse=True)
    if not bodies or any(abs(part.volume) > 1.0 for part in bodies[1:]):
        raise ValueError("The arch cover has separate printable pieces")
    mesh = bodies[0]
    trimesh.smoothing.filter_humphrey(mesh, alpha=0.1, beta=0.5, iterations=32)
    trimesh.repair.fix_normals(mesh)
    if not mesh.is_volume:
        raise ValueError("The arch cover is not one closed solid")
    return mesh

def render_scene(image: Image.Image, rect, camera, objects):
    x0, y0, x1, y1 = rect
    eye = np.asarray(camera, dtype=float)
    target = np.array((0.0, -10.0, 19.0))
    forward = target - eye
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.array((0.0, 0.0, 1.0)))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    light = np.array((0.6, -0.7, 1.0))
    light /= np.linalg.norm(light)
    allv = np.concatenate([mesh.vertices for mesh, _ in objects])
    base_xy = np.column_stack(((allv - target) @ right, (allv - target) @ up))
    ext = np.ptp(base_xy, axis=0)
    scale = min((x1 - x0 - 70) / ext[0], (y1 - y0 - 70) / ext[1])
    cx = (x0 + x1) / 2 - scale * (base_xy[:, 0].min() + base_xy[:, 0].max()) / 2
    cy = (y0 + y1) / 2 + scale * (base_xy[:, 1].min() + base_xy[:, 1].max()) / 2
    pixels = np.asarray(image).copy()
    depth_buffer = np.full((image.height, image.width), np.inf, dtype=np.float32)
    min_x, min_y, max_x, max_y = (int(v) for v in rect)
    for mesh, base in objects:
        verts = np.asarray(mesh.vertices)
        vertex_normals = np.asarray(mesh.vertex_normals)
        projected = np.column_stack((cx + scale * ((verts - target) @ right),
                                     cy - scale * ((verts - target) @ up)))
        depths = (verts - eye) @ forward
        for face, n in zip(mesh.faces, mesh.face_normals):
            if np.dot(n, -forward) <= 0:
                continue
            poly = projected[face]
            xlo = max(min_x, int(math.floor(np.min(poly[:, 0]))))
            xhi = min(max_x, int(math.ceil(np.max(poly[:, 0]))))
            ylo = max(min_y, int(math.floor(np.min(poly[:, 1]))))
            yhi = min(max_y, int(math.ceil(np.max(poly[:, 1]))))
            if xlo >= xhi or ylo >= yhi:
                continue
            x_a, y_a = poly[0]
            x_b, y_b = poly[1]
            x_c, y_c = poly[2]
            denominator = (y_b-y_c)*(x_a-x_c) + (x_c-x_b)*(y_a-y_c)
            if abs(denominator) < 1e-9:
                continue
            yy, xx = np.mgrid[ylo:yhi, xlo:xhi]
            xx = xx + 0.5
            yy = yy + 0.5
            w0 = ((y_b-y_c)*(xx-x_c) + (x_c-x_b)*(yy-y_c)) / denominator
            w1 = ((y_c-y_a)*(xx-x_c) + (x_a-x_c)*(yy-y_c)) / denominator
            w2 = 1 - w0 - w1
            inside = (w0 >= -1e-7) & (w1 >= -1e-7) & (w2 >= -1e-7)
            if not inside.any():
                continue
            tri_depth = w0*depths[face[0]] + w1*depths[face[1]] + w2*depths[face[2]]
            current_depth = depth_buffer[ylo:yhi, xlo:xhi]
            closer = inside & (tri_depth < current_depth)
            if not closer.any():
                continue
            interpolated = w0[..., None] * vertex_normals[face[0]] + \
                w1[..., None] * vertex_normals[face[1]] + \
                w2[..., None] * vertex_normals[face[2]]
            normal_length = np.maximum(1e-9, np.linalg.norm(interpolated, axis=2))
            brightness = np.clip((interpolated @ light) / normal_length, 0.0, 1.0)
            shade = 0.60 + 0.40 * brightness
            current_depth[closer] = tri_depth[closer]
            pixels[ylo:yhi, xlo:xhi][closer] = np.clip(
                np.asarray(base) * shade[..., None], 0, 255)[closer].astype(np.uint8)
    image.paste(Image.fromarray(pixels))

def render_preview(cap: trimesh.Trimesh, jaw: trimesh.Trimesh):
    upper = load_stl_mm(UPPER_STL)
    face = load_stl_mm(FACE_STL)
    eye_part = load_stl_mm(EYE_STL)
    image = Image.new("RGB", (1500, 800), (247, 249, 251))
    draw = ImageDraw.Draw(image)
    font_path = "/System/Library/Fonts/Supplemental/Arial.ttf"
    heading = ImageFont.truetype(font_path, 25) if Path(font_path).exists() else ImageFont.load_default()
    caption = ImageFont.truetype(font_path, 17) if Path(font_path).exists() else ImageFont.load_default()
    draw.text((55, 28), "MICRODUCK  /  CENTRE-PART HAIRSTYLE", font=heading, fill=(32, 41, 52))
    draw.text((55, 66), "Fitted hollow cap · parted fringe · sculpted side panels", font=caption, fill=(79, 90, 105))
    objects = [(jaw, (246, 119, 58)), (face, (128, 134, 140)),
               (eye_part, (245, 202, 67)), (upper, (133, 140, 148)), (cap, (181, 185, 190))]
    render_scene(image, (45, 110, 750, 680), (0, -180, 35), objects)
    render_scene(image, (755, 110, 1460, 680), (180, 0, 40), objects)
    draw = ImageDraw.Draw(image)
    draw.text((110, 695), "FRONT VIEW", font=caption, fill=(63, 75, 90))
    draw.text((830, 695), "SIDE VIEW  ·  HINGE ZONE", font=caption, fill=(63, 75, 90))
    draw.text((55, 750), f"Static jaw gap: {cap.bounds[0, 2] - jaw.bounds[1, 2]:.1f} mm. Check full mouth travel on the physical robot.",
              font=caption, fill=(122, 82, 53))
    image.save(OUT_PREVIEW)
    angle_image = Image.new("RGB", (1000, 900), (247, 249, 251))
    render_scene(angle_image, (50, 50, 950, 850), (140, -180, 75), objects)
    angle_image.save(OUT_ANGLE)


def validate_static_clearance(cap: trimesh.Trimesh) -> None:
    """Reject overlap with available fixed and moving part surfaces."""
    solid = cap.voxelized(0.35).fill()
    for part in (UPPER_STL, FACE_STL, EYE_STL, LOWER_STL,
                 SOFT_MOUTH_TOP_STL, SOFT_JAW_STL,
                 BOTTOM_SHELL_STL, MOTOR_SUPPORT_STL):
        mesh = load_stl_mm(part)
        surface_points = np.vstack((mesh.vertices, mesh.triangles_center))
        if solid.is_filled(surface_points).any():
            raise ValueError(f"Hairstyle intersects the source part: {part.name}")


def main():
    final = make_hull_cover()
    if not isinstance(final, trimesh.Trimesh) or not final.is_watertight or final.volume <= 0:
        raise ValueError("The hairstyle is not one printable solid")
    jaw = load_stl_mm(LOWER_STL)
    z_gap = final.bounds[0, 2] - jaw.bounds[1, 2]
    if z_gap < 5.0:
        raise ValueError(f"Static jaw clearance is only {z_gap:.2f} mm")
    validate_static_clearance(final)
    final.export(OUT_STL)
    render_preview(final, jaw)
    print(f"STL: {OUT_STL}")
    print(f"mesh: {len(final.faces)} triangles, {final.body_count} body, watertight={final.is_watertight}")
    print(f"bounds (mm): {np.round(final.bounds, 2).tolist()}")
    print(f"nominal static jaw vertical clearance: {z_gap:.2f} mm")


if __name__ == "__main__":
    main()
