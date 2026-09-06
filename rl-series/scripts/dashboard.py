#!/usr/bin/env python3
"""duck-dashboard — Microduck RL 本地可视化操作台（纯标准库，无额外依赖）。

启动:  python3 rl-series/scripts/dashboard.py        （然后浏览器开 http://localhost:8090）
功能:  状态面板（训练进度/奖励）· 一键操作（启动/停止训练、回放捕获、viser、TensorBoard）
       · checkpoint 选择器 · 产物画廊（回放 GIF / 对比图）

设计原则：GET 永不阻塞；长任务用 start_new_session 派生后台进程，页面刷新看结果。
"""

import glob
import html
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[2]          # microduck-replica
RL = ROOT / "upstream" / "microduck_rl"
ASSETS = ROOT / "rl-series" / "assets"
PORT = 8090
EXP_LOG = "/tmp/expC.log"


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def train_running() -> bool:
    return sh(["pgrep", "-f", "uv run train"]).returncode == 0


def train_status() -> str:
    if not train_running():
        return "⚪ 无训练进程"
    try:
        log = Path("/tmp/expC.log").read_text(errors="ignore").splitlines()
        it = [l for l in log if "Learning iteration" in l]
        rw = [l for l in log if "Mean reward" in l]
        tail = (it[-1].strip() if it else "") + " ｜ " + (rw[-1].strip() if rw else "")
        return f"🟢 训练进行中 ｜ {html.escape(tail)}"
    except FileNotFoundError:
        return "🟢 训练进行中（日志未找到）"


def checkpoints() -> list[str]:
    pts = glob.glob(str(RL / "logs/rsl_rl/velocity/*/model_*.pt"))
    return sorted(pts, key=os.path.getmtime, reverse=True)


def launch(args, log=None):
    """派生不随本服务退出的后台进程。"""
    out = open(log, "ab") if log else subprocess.DEVNULL
    subprocess.Popen(args, cwd=str(RL), stdout=out, stderr=subprocess.STDOUT,
                     start_new_session=True)


def do_action(qs: dict) -> str:
    act = qs.get("action", [""])[0]
    ckpt = qs.get("ckpt", [""])[0]
    if act == "start_train":
        if train_running():
            return "训练已在运行，忽略。"
        launch(["uv", "run", "train", "Mjlab-Velocity-Flat-MicroDuck",
                "--env.scene.num-envs", "64", "--agent.max_iterations", "2100",
                "--agent.logger", "tensorboard", "--agent.resume", "True",
                "--agent.load_run", "2026-09-06_01-39-55_exp001-a",
                "--agent.load_checkpoint", "model_99.pt",
                "--agent.run_name", "expC-cpu2000"], log="/tmp/expC.log")
        return "已提交：续训从 model_99 继续（日志 /tmp/expC.log）。"
    if act == "stop_train":
        sh(["pkill", "-f", "uv run train"])
        return "已停止训练进程。"
    if act == "capture":
        if not ckpt:
            return "未选择 checkpoint。"
        label = f"面板-{Path(ckpt).parent.name.split('_')[-1]}-{Path(ckpt).stem}"
        launch(["uv", "run", "python", str(ROOT / "rl-series/scripts/capture_rollout.py"),
                "--ckpt", ckpt, "--label", label])
        return f"已提交回放捕获：{label}（约 2 分钟，完成后出现在下方画廊）。"
    if act == "start_viser":
        launch(["bash", str(ROOT / "rl-series/scripts/serve_play.sh"), ckpt or ""])
        return "已提交：viser 服务器就绪后打开 http://localhost:8080"
    if act == "start_tb":
        launch(["uv", "run", "tensorboard", "--logdir", "logs/rsl_rl", "--port", "6006"])
        return "已提交：TensorBoard 就绪后打开 http://localhost:6006"
    return "未知操作。"


def page(msg: str = "") -> str:
    ckpts = checkpoints()
    ckpt_opts = "".join(
        f'<option value="{html.escape(c)}">{html.escape(Path(c).parent.name + "/" + Path(c).name)}</option>'
        for c in ckpts[:24])
    gallery = ""
    for f in sorted(glob.glob(str(ASSETS / "*.gif")) + glob.glob(str(ASSETS / "exp0*.png")),
                    key=os.path.getmtime, reverse=True)[:12]:
        rel = os.path.relpath(f, str(ASSETS))
        if f.endswith(".gif"):
            gallery += f'<div class="card"><img src="/assets/{html.escape(rel)}"><p>{html.escape(rel)}</p></div>'
        else:
            gallery += (f'<div class="card"><a href="/assets/{html.escape(rel)}">'
                        f'<img src="/assets/{html.escape(rel)}"></a><p>{html.escape(rel)}</p></div>')
    msg_html = f'<div class="msg">{html.escape(msg)}</div>' if msg else ""
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="15"><title>Microduck RL 操作台</title>
<style>
body{{font-family:-apple-system,'PingFang SC',sans-serif;background:#0f1115;color:#e6e6e6;
     margin:0;padding:20px;max-width:1100px;margin:auto}}
h1{{font-size:1.3em}} h2{{font-size:1.05em;color:#8ab4f8;margin:18px 0 6px}}
.box{{background:#1a1d24;border-radius:10px;padding:14px 18px;margin:10px 0}}
.status{{font-size:1.1em}}
form{{display:inline;margin-right:10px}}
button{{background:#2d7ff9;color:white;border:0;border-radius:6px;padding:8px 14px;
       margin:3px 2px;cursor:pointer;font-size:.95em}}
button.red{{background:#d33}} button.gray{{background:#555}}
select{{background:#111;color:#eee;padding:6px;border-radius:6px;max-width:420px}}
.msg{{background:#2b4d16;border-radius:8px;padding:10px;margin:10px 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}}
.card{{background:#22262f;border-radius:8px;padding:8px}} .card img{{width:100%;border-radius:6px}}
.card p{{font-size:.75em;color:#9aa;margin:4px 0 0;word-break:break-all}}
a{{color:#8ab4f8}} .dim{{color:#9aa;font-size:.85em}}
</style></head><body>
<h1>🦆 Microduck RL 操作台 <span class="dim">（本页每 15 秒自动刷新）</span></h1>
{msg_html}
<div class="box status">{train_status()}</div>

<h2>操作（点一下执行）</h2>
<div class="box">
  <form method="post" action="/do"><input type="hidden" name="action" value="start_train">
    <button>▶ 启动续训（expC，2000 迭代）</button></form>
  <form method="post" action="/do"><input type="hidden" name="action" value="stop_train">
    <button class="red">⏹ 停止训练</button></form>
  <form method="post" action="/do"><input type="hidden" name="action" value="start_tb">
    <button class="gray">📈 启动 TensorBoard</button></form>
  <a href="http://localhost:6006" target="_blank"><button class="gray">打开 TensorBoard 页面</button></a>
  <a href="http://localhost:8080" target="_blank"><button class="gray">打开 3D 回放 (viser)</button></a>
</div>

<div class="box">
  <h2 style="margin-top:0">🎬 回放捕获（选 checkpoint → 点捕获 → 约 2 分钟出 GIF）</h2>
  <form method="post" action="/do">
    <select name="ckpt">{ckpt_opts}</select>
    <input type="hidden" name="action" value="capture">
    <button>🎥 捕获回放 GIF</button></form>
  <form method="post" action="/do"><input type="hidden" name="action" value="start_viser">
    <button class="gray">用选中 checkpoint 启动 viser 实时查看</button></form>
</div>

<h2>产物画廊（最新在前）</h2>
<div class="grid">{gallery or "<p class='dim'>暂无产物</p>"}</div>

<p class="dim">手册：rl-series/30天计划.md · 实验：rl-series/experiments/ ·
服务器日志：/tmp/expC.log、/tmp/viser_server.log</p>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype="text/html; charset=utf-8"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/assets/"):
            f = ASSETS / self.path[len("/assets/"):]
            if f.resolve().is_relative_to(ASSETS.resolve()) and f.exists():
                mime = "image/gif" if f.suffix == ".gif" else "image/png"
                self._send(f.read_bytes(), mime)
            else:
                self.send_error(404)
        else:
            self._send(page().encode())

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        msg = do_action(parse_qs(self.rfile.read(n).decode()))
        self._send(page(msg).encode())

    def log_message(self, *a):  # 静默访问日志
        pass


if __name__ == "__main__":
    print(f"dashboard on http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
