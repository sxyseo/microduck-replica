"""生成孔径测试片 STL —— 复刻打印的前置定标件（docs/打印工艺调整表.md 第二节）。

用法（任意目录）:
    uv run --with shapely --with mapbox_earcut --with trimesh --with numpy \
        python scripts/generate_test_coupon.py

产出: print/测试片/ 下两个 STL + 一份图例说明
  1. 测试片-孔径-80x50x4.stl   M2 过孔 / 攻丝底孔阶梯
  2. 测试块-轴承22-55x20x4.stl Ø22 轴承压入三档
  3. 测试块-轴承15-55x20x4.stl Ø15 轴承压入三档

原理：底板 = 带圆孔的矩形轮廓挤出（shapely 建轮廓、mapbox_earcut 三角化）。
所有尺寸是**设计值**，打印后用游标卡尺实测哪个孔"刚好"，那就是你这台机器的补偿值。
"""

from pathlib import Path

import numpy as np
import shapely
import trimesh
from shapely.geometry import Polygon

OUT_DIR = Path(__file__).resolve().parent.parent / "print" / "测试片"
THICK = 4.0


def plate_with_holes(width, height, holes) -> trimesh.Trimesh:
    """矩形板 + 圆形通孔列表 [(cx, cy, 直径)]，原点在左下角，挤出 THICK 厚。"""
    outer = shapely.box(0, 0, width, height)
    polys = [shapely.Point(cx, cy).buffer(d / 2, quad_segs=32) for cx, cy, d in holes]
    poly = Polygon(outer.exterior.coords, [p.exterior.coords for p in polys])
    mesh = trimesh.creation.extrude_polygon(poly, height=THICK)
    return mesh


def write(mesh: trimesh.Trimesh, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    mesh.export(path)
    print(f"written {path}  bbox={np.round(mesh.bounds[1] - mesh.bounds[0], 1)}")


def main() -> None:
    # 1) M2 孔径阶梯片 80×50
    #    第一行 y=36：M2 过孔阶梯 Ø2.2 / 2.3 / 2.4 / 2.5（找"螺丝刚好能过"的那个）
    #    第二行 y=24：攻丝底孔阶梯 Ø1.60 / 1.65 / 1.70 / 1.75（找"自攻拧得进不裂"的那个）
    #    第三行 y=12：沉头参考 Ø4.4 通孔 + Ø3.0 / Ø2.7 参考
    holes = []
    xs = [12, 30, 48, 66]
    for x, d in zip(xs, [2.2, 2.3, 2.4, 2.5]):
        holes.append((x, 36, d))
    for x, d in zip(xs, [1.60, 1.65, 1.70, 1.75]):
        holes.append((x, 24, d))
    for x, d in zip(xs, [4.4, 3.0, 2.7, 2.2]):
        holes.append((x, 12, d))
    write(plate_with_holes(78, 46, holes), "测试片-M2孔径阶梯-78x46x4.stl")

    # 2) Ø22×16×4 轴承压入三档（躯干/腿部主轴承）：过盈 / 过渡 / 间隙
    #    孔径 22.1 > 板高，板高必须 ≥ 26；孔心间距 ≥ 22.2 防止两孔相交
    holes22 = [(14, 13, 21.9), (38, 13, 22.0), (62, 13, 22.1)]
    write(plate_with_holes(76, 26, holes22), "测试块-轴承22x16x4压入三档-76x26x4.stl")

    # 3) Ø15×10×3 轴承压入三档（头颈轴承）
    holes15 = [(10, 9, 14.9), (27.5, 9, 15.0), (45, 9, 15.1)]
    write(plate_with_holes(55, 18, holes15), "测试块-轴承15x10x3压入三档-55x18x4.stl")


if __name__ == "__main__":
    main()
