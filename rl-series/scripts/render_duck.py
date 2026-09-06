"""渲染 Microduck MJCF 静态图（文章配图 / 封面用）。

用法:
    python scripts/render_duck.py <microduck_rl 根目录> <输出目录>

需要 MuJoCo 自带离屏渲染可用（macOS / 带显存的 Linux 均可）。
XML 内的资源路径是相对的，所以先把它复制到同目录的临时文件再加载。
"""

import os
import shutil
import sys

import mujoco


def render(rl_root: str, out_dir: str) -> list[str]:
    src = os.path.join(
        rl_root, "src", "mjlab_microduck", "robot", "microduck", "robot_allcollisions.xml"
    )
    tmp = os.path.join(os.path.dirname(src), "_series_render_tmp.xml")
    shutil.copyfile(src, tmp)
    # 原模型没有灯，注入一盏平行光，否则整帧近黑
    html = open(tmp).read()
    html = html.replace(
        "<worldbody>",
        '<worldbody><light directional="true" pos="0.3 -0.5 1" dir="0.3 0.5 -1" '
        'diffuse="0.9 0.9 0.9" specular="0.3 0.3 0.3" ambient="0.25 0.25 0.25"/>',
        1,
    )
    open(tmp, "w").write(html)
    try:
        model = mujoco.MjModel.from_xml_path(tmp)
        model.vis.global_.offwidth = 1440  # MJCF 里默认 640，不够出图
        model.vis.global_.offheight = 1080
        data = mujoco.MjData(model)
        # 落到 HOME 姿态附近：先 forward 一遍让默认姿态生效
        mujoco.mj_forward(model, data)

        renderer = mujoco.Renderer(model, height=1080, width=1440)
        shots = []
        # (名字, 方位角, 仰角, 距离, 看向点 xyz)
        views = [
            ("03-四分之三", -135, -12, 0.55, (0.0, 0.0, 0.12)),
            ("01-正面", -90, -10, 0.5, (0.0, 0.0, 0.12)),
            ("02-侧面", 0, -10, 0.5, (0.0, 0.0, 0.12)),
        ]
        for name, az, el, dist, lookat in views:
            cam = mujoco.MjvCamera()
            cam.type = mujoco.mjtCamera.mjCAMERA_FREE
            cam.lookat[:] = lookat
            cam.distance = dist
            cam.azimuth = az
            cam.elevation = el
            renderer.update_scene(data, camera=cam)
            out = os.path.join(out_dir, f"duck-render-{name}.png")
            _save(renderer.render(), out)
            shots.append(out)
            print("saved", out)
        renderer.close()
        return shots
    finally:
        os.remove(tmp)


def _save(img, path):
    import PIL.Image

    PIL.Image.fromarray(img).save(path)


if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2])
