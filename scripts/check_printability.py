"""打印就绪检查：对 print/打印件/ 全部 STL 做可打印性体检，并与孔特征数据关联。

用法（在 microduck-replica 仓库根目录）:
    upstream/microduck_rl/.venv/bin/python scripts/check_printability.py

输出: docs/打印就绪检查.md
依赖: trimesh（rl venv 已有）、numpy、docs/hole_analysis.json

检查项: 水密性(是否可切片)、法向一致性、退化面、体积/包围盒、孔位清单。
不检查: 最小壁厚/悬垂 —— 那类要切片器视角，报告里给了操作建议而不是假数字。
"""

import json
import re
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parent.parent
PRINT_DIR = ROOT / "print" / "打印件"
HOLES_JSON = ROOT / "docs" / "hole_analysis.json"
OUT_MD = ROOT / "docs" / "打印就绪检查.md"

# print/README.md 的数量表（几何引用计数）
QUANTITIES = {
    "leg": 4, "hip_l": 2, "neck": 2, "power_support": 2,
    "sole_left": 2, "sole_right": 2, "upper_leg_rigidity_plate": 2,
    "yaw2roll": 2, "bearing_roll": 2,
}

UPSTREAM_RE = re.compile(r"^([A-Za-z0-9_]+?)_(?=[^\x00-\x7F])")


def upstream_name(path: Path, known_keys: list[str]) -> str:
    """打印件文件名前缀 → 上游网格名。优先对已知键做最长匹配（处理
    m12_lens_holder_M12镜头座 这类上游名里带下划线/数字的情况）。"""
    stem = path.stem
    best = ""
    for k in known_keys:
        if stem == k or stem.startswith(k + "_"):
            if len(k) > len(best):
                best = k
    if best:
        return best
    m = UPSTREAM_RE.match(stem)
    return m.group(1) if m else stem


def check_mesh(path: Path) -> dict:
    # process=True 会合并重复顶点 —— STL 天然每三角独立存顶点，不合并必误报非水密
    mesh = trimesh.load(path, force="mesh", process=True)
    ext = mesh.bounds[1] - mesh.bounds[0]
    scale = 1000.0 if float(ext.max()) < 1.0 else 1.0  # MJCF STL 单位是米 → 毫米
    mesh.apply_scale(scale)
    r = {
        "faces": len(mesh.faces),
        "watertight": bool(mesh.is_watertight),
        "winding": bool(mesh.is_winding_consistent),
        "volume_cm3": None,
        "bbox": None,
        "degenerate": int(np.sum(mesh.area_faces <= 1e-9)),
    }
    if r["watertight"]:
        r["volume_cm3"] = abs(mesh.volume) / 1000.0  # mm³ → cm³
    b = mesh.bounds
    ext = b[1] - b[0]
    r["bbox"] = tuple(round(float(v), 1) for v in ext)
    return r


def hole_summary(upstream: str, holes: dict) -> tuple[int, int, int, str]:
    """返回 (Ø2.2过孔, Ø4.4沉头, Ø1.6攻丝, 其他孔直径描述)"""
    entry = holes.get(upstream + ".stl")
    if not entry:
        return 0, 0, 0, "—"
    c22 = sum(1 for h in entry if abs(h["直径mm"] - 2.2) < 0.15)
    c44 = sum(1 for h in entry if abs(h["直径mm"] - 4.4) < 0.15)
    c16 = sum(1 for h in entry if abs(h["直径mm"] - 1.6) < 0.15)
    others = sorted({h["直径mm"] for h in entry
                     if abs(h["直径mm"] - 2.2) >= 0.15
                     and abs(h["直径mm"] - 4.4) >= 0.15
                     and abs(h["直径mm"] - 1.6) >= 0.15})
    if not others:
        return c22, c44, c16, "—"
    shown = "、".join(f"Ø{d:g}" for d in others[:4])
    tail = f" 等共{len(others)}种" if len(others) > 4 else ""
    return c22, c44, c16, shown + tail


def main() -> None:
    holes = json.loads(HOLES_JSON.read_text())
    known = [k[:-4] for k in holes if k.endswith(".stl")]  # 去掉 .stl 后缀
    rows, total_qty = [], 0
    agg = dict(q22=0, q44=0, q16=0)
    problems = []

    for stl in sorted(PRINT_DIR.glob("*.stl")):
        name = stl.stem
        up = upstream_name(stl, known)
        qty = QUANTITIES.get(up, 1)
        total_qty += qty
        m = check_mesh(stl)
        c22, c44, c16, oth = hole_summary(up, holes)
        agg["q22"] += c22 * qty
        agg["q44"] += c44 * qty
        agg["q16"] += c16 * qty

        if m["watertight"] and m["winding"] and m["degenerate"] == 0:
            verdict = "✅ 可直接切片"
        elif m["watertight"]:
            verdict = "⚠️ 水密但法向需修（fix_normals）"
            problems.append((name, "法向不一致"))
        else:
            verdict = "❌ 非水密（补洞后再切）"
            problems.append((name, "非水密"))

        vol = f'{m["volume_cm3"]:.1f}' if m["volume_cm3"] is not None else "—"
        rows.append(
            f'| {name} | ×{qty} | {m["faces"]} | {"是" if m["watertight"] else "**否**"} '
            f'| {"是" if m["winding"] else "否"} | {vol} | '
            f'{m["bbox"][0]}×{m["bbox"][1]}×{m["bbox"][2]} | '
            f'{c22} | {c44} | {c16} | {oth} | {verdict} |'
        )

    md = f"""# 打印就绪检查（{PRINT_DIR.name}/ 全量体检）

> 由 `scripts/check_printability.py` 自动生成。检查项：水密性、法向一致性、退化面、
> 体积与包围盒；孔位来自 `docs/hole_analysis.json`（STL 圆柱特征反推）。
> **不包含**最小壁厚与悬垂分析 —— 请在切片器里开「细墙/悬垂检测」过一遍。

## 结论速览

- 共 **{len(rows)} 种 / {total_qty} 件**（数量按上游引用计数，见 `print/README.md`）
- 可直接切片：**{sum(1 for r in rows if "✅" in r)} 种**
- 需要修法向：**{sum(1 for r in rows if "⚠️" in r)} 种**　非水密：**{sum(1 for r in rows if "❌" in r)} 种**
- 全机 M2 孔位总量：过孔 Ø2.2 ×{agg["q22"]}｜沉头 Ø4.4 ×{agg["q44"]}｜攻丝底孔 Ø1.6 ×{agg["q16"]}
  （按打印数量加权；**打印后孔径会缩小 0.1–0.3mm，处理办法见 [打印工艺调整表](打印工艺调整表.md)**）

## 明细

| 零件 | 数量 | 面数 | 水密 | 法向 | 体积cm³ | 包围盒mm | Ø2.2 | Ø4.4 | Ø1.6 | 其他孔 | 结论 |
|---|---|---|---|---|---|---|---|---|---|---|---|
{chr(10).join(rows)}

## 需要处理的零件

{chr(10).join(f'- **{n}**：{why}' for n, why in problems) or "- 无 🎉"}

> 修复办法：`trimesh.repair.fix_normals(m)` / `trimesh.repair.fill_holes(m)`，
> 或切片器自带工具（PrusaSlicer「修复」按钮）。修完重跑本脚本确认。
"""
    OUT_MD.write_text(md)
    print(f"written {OUT_MD} — {len(rows)} parts, problems: {len(problems)}")


if __name__ == "__main__":
    main()
