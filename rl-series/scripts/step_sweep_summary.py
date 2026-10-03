#!/usr/bin/env python3
"""step_sweep_summary.py — 把课 6 阶跃扫描的 CSV 批量汇总成辨识表。

输入：`hl2915_step_id<id>_kp<P>_kd<D>[-<run>].csv`（hl2915_bench.py 课 6 的产物）。
输出：每组 (P, D) 的超调/稳态误差/整定时间/峰速/峰值电流，以及 up/back
两向稳态误差之差（回差佐证）——即换舵机重训全流程.md §2.2「PD 阶跃响应」
一行要的辨识表。指标语义与 hl2915_bench.py 的 step_metrics() 逐条一致
（含 tol = 死区 3 + 2 = 5 步），只是从"单次跑完即打印"变成"跨文件跨轮次汇总"。

用法：
    python3 step_sweep_summary.py                     # 汇总脚本同目录的全部匹配 CSV
    python3 step_sweep_summary.py a.csv b.csv         # 指定文件
    python3 step_sweep_summary.py --tol 5 --out x.md  # 自定义容差/输出路径

HL-1910 到货后：同一条命令重跑一遍即可产出 1910 的辨识表（记得按 7.4V 电压窗重采）。
"""
import argparse
import csv
import re
import sys
from pathlib import Path

TOL_DEFAULT = 5          # bench: DEAD_ZONE_STEPS(3) + 2
PHASES = ("up", "back")  # pre 段只是静置基线，不参与指标

NAME_RE = re.compile(r"hl2915_step_id(?P<id>\d+)_kp(?P<kp>\d+)_kd(?P<kd>\d+)(?:-(?P<run>\d+))?\.csv$")


def load_phases(path):
    """读一个课 6 CSV → {phase: (target, [(t_ms, pos, speed, load, current_ma), ...])}。

    丢包行（pos 为空）跳过——bench 落盘时故意保留时间格，汇总时不让空行参与均值。
    """
    phases = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if not row["pos"]:
                continue
            ph = row["phase"]
            rec = (int(row["t_ms"]), float(row["pos"]), float(row["speed"] or 0),
                   float(row["load"] or 0), float(row["current_ma"] or 0))
            phases.setdefault(ph, [float(row["target"]), []])[1].append(rec)
    return phases


def step_metrics(pts, target, tol):
    """与 hl2915_bench.py step_metrics() 同语义：超调/稳态误差/整定/峰速/峰值电流。"""
    if len(pts) < 5:
        return None
    p0 = pts[0][1]
    travel = target - p0
    if abs(travel) < 10:
        return None
    tail = [p for _, p, *_ in pts[-10:]]
    err = sum(tail) / len(tail) - target
    dirn = 1 if travel > 0 else -1
    extreme = max(p for _, p, *_ in pts) if dirn > 0 else min(p for _, p, *_ in pts)
    over_steps = max(0.0, (extreme - target) * dirn)
    settle_ms = None
    for i in range(len(pts)):
        if all(abs(p - target) <= tol for _, p, *_ in pts[i:]):
            settle_ms = pts[i][0]
            break
    return {
        "err": err,
        "over_pct": 100.0 * over_steps / abs(travel),
        "settle_ms": settle_ms,
        "vmax": max(abs(v) for _, _, v, _, _ in pts),
        "imax": max(c for *_, c in pts),
        "load_max": max(l for _, _, _, l, _ in pts),
    }


def run_motion(phases):
    """该文件里舵机到底动没动：任一 phase 相对段首位移 >10 步即算动。

    现库里的课 6 CSV 大多是"锁死零响应"的取证记录（判坏期所录，err≈−travel、
    峰速≈0）——它们对辨识毫无用处，必须先分拣，否则辨识表全是假数据。
    """
    for target, pts in phases.values():
        if len(pts) < 5:
            continue
        p0 = pts[0][1]
        if max(abs(p - p0) for _, p, *_ in pts) > 10:
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="*", help="课 6 CSV（缺省 = 脚本目录下全部匹配文件）")
    ap.add_argument("--tol", type=float, default=TOL_DEFAULT, help="整定容差（步），默认 5")
    ap.add_argument("--out", help="汇总 Markdown 路径（缺省 = 脚本目录 hl2915_step_sweep_summary.md）")
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    files = [Path(p) for p in args.files] or sorted(
        p for p in here.glob("hl2915_step_id*_kp*.csv") if NAME_RE.search(p.name))
    if not files:
        sys.exit("没找到匹配 hl2915_step_id*_kp*.csv 的文件")

    groups = {}       # (kp, kd) → [run dict]（只收有效扫描）
    dead_runs = []    # 零响应取证（判坏期所录），单独列出
    for path in files:
        m = NAME_RE.search(path.name)
        if not m:
            sys.exit(f"文件名不认识（要 hl2915_step_id*_kp*_kd*.csv）：{path.name}")
        run = {"name": path.name, "id": int(m["id"]),
               "kp": int(m["kp"]), "kd": int(m["kd"]), "phases": {}}
        phases = load_phases(path)
        if not run_motion(phases):
            dead_runs.append(run)
            continue
        for ph in PHASES:
            if ph not in phases:
                continue
            target, pts = phases[ph]
            run["phases"][ph] = step_metrics(pts, target, args.tol)
        groups.setdefault((run["kp"], run["kd"]), []).append(run)

    lines = ["# HL-2915 阶跃扫描汇总（课 6 → 辨识表）", "",
             f"- 来源：{len(files)} 个 CSV × tol ±{args.tol:g} 步（与 bench step_metrics 同语义）",
             "- 指标：稳态误差 = 末 10 样均值 − 目标；整定 = 之后一直留在容差带内的首时刻；"
             "up/back 稳态误差之差 ≈ 回差佐证（≠正式回差）",
             "- 记账位：换舵机重训全流程.md §2.2「PD 阶跃响应」→ 最终填 "
             "`upstream/microduck_rl/.../robot/microduck_constants.py` 与 BAM 参数", ""]

    if dead_runs:
        lines += [f"## ⚠️ 零响应取证（{len(dead_runs)} 个文件，未进辨识表）", "",
                  "全程位移 ≤10 步、峰速 ≈0 —— 判坏期录下的锁死状态，只有取证价值，"
                  "不能当辨识数据。如需辨识请 REBOOT 清锁确认健康后重跑课 6。", ""]
        lines += ["| 文件 | P | D |", "|---|---|---|"]
        for r in sorted(dead_runs, key=lambda x: x["name"]):
            lines.append(f"| `{r['name']}` | {r['kp']} | {r['kd']} |")
        lines.append("")

    def fmt(v, unit="", nd=1):
        return "—" if v is None else f"{v:.{nd}f}{unit}"

    lines += ["## 每组增益（跨轮次均值）", ""]
    if not groups:
        lines += ["*（暂无有效扫描——现有文件全部是零响应取证。"
                  "健康舵机重跑课 6 后本表自动出现。）*", ""]
    else:
        lines += ["| P | D | 轮次 | up 稳态误差(步) | up 超调 | up 整定 | back 稳态误差(步) | back 超调 | back 整定 | 回差佐证(步) | 峰速(步/s) | 峰值电流(mA) |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for (kp, kd), runs in sorted(groups.items()):
        agg = {}
        for ph in PHASES:
            ms = [r["phases"][ph] for r in runs if ph in r["phases"] and r["phases"][ph]]
            for k in ("err", "over_pct", "settle_ms", "vmax", "imax"):
                vals = [m[k] for m in ms if m[k] is not None]
                agg[f"{ph}_{k}"] = sum(vals) / len(vals) if vals else None
        settle = {ph: agg.get(f"{ph}_settle_ms") for ph in PHASES}
        hyst = (agg["up_err"] - agg["back_err"]
                if agg.get("up_err") is not None and agg.get("back_err") is not None else None)
        lines.append(
            f"| {kp} | {kd} | {len(runs)} "
            f"| {fmt(agg.get('up_err'))} | {fmt(agg.get('up_over_pct'), '%')} "
            f"| {fmt(settle['up'], 'ms', 0) if settle['up'] is not None else '未整定'} "
            f"| {fmt(agg.get('back_err'))} | {fmt(agg.get('back_over_pct'), '%')} "
            f"| {fmt(settle['back'], 'ms', 0) if settle['back'] is not None else '未整定'} "
            f"| {fmt(hyst, nd=1)} | {fmt(agg.get('up_vmax'), nd=0)} | {fmt(agg.get('up_imax'), nd=0)} |")
    lines.append("")

    if groups:
        lines += ["## 单文件明细", "",
                  "| 文件 | phase | 稳态误差(步) | 超调 | 整定 | 峰速(步/s) | 峰值电流(mA) | 峰值负载 |",
                  "|---|---|---|---|---|---|---|---|"]
        for (kp, kd), runs in sorted(groups.items()):
            for r in sorted(runs, key=lambda x: x["name"]):
                for ph in PHASES:
                    m = r["phases"].get(ph)
                    if not m:
                        continue
                    settle = (f"{m['settle_ms']:.0f}ms" if m["settle_ms"] is not None else "未整定")
                    lines.append(f"| `{r['name']}` | {ph} | {m['err']:+.1f} | {m['over_pct']:.1f}% "
                                 f"| {settle} | {m['vmax']:.0f} | {m['imax']:.0f} | {m['load_max']:.0f} |")
        lines.append("")

    lines += ["## 怎么读这张表（选 P/D 工作点的判据）", "",
              "- **稳且刚**：稳态误差小 + 超调 <10% + 整定快，三者不可兼得时先保不超调（腿上震荡比迟钝危险）。",
              "- **回差佐证列**：|值| 持续偏大 → 先查机械间隙/装架，再怀疑参数。",
              "- 本表只覆盖 kp/kd 两参；堵转力矩-速度、摩擦、armature、指令延迟仍缺，"
              "采集清单见 换舵机重训全流程.md §2.2。", ""]

    report = "\n".join(lines)
    out = Path(args.out) if args.out else here / "hl2915_step_sweep_summary.md"
    out.write_text(report)
    print(report)
    print(f"→ 已写入 {out}")


if __name__ == "__main__":
    main()
