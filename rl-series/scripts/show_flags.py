"""列出 microduck_velocity_env_cfg.py 里全部开关的当前值与行号（正则解析，免导入 mjlab）。

用法:
    python scripts/show_flags.py <microduck_rl 根目录>
"""

import re
import sys

path = sys.argv[1] + "/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py"
pat = re.compile(r"^(ENABLE_\w+|TURN_IN_PLACE_FRACTION|USE_PROJECTED_GRAVITY)\s*=\s*(.+?)\s*(#.*)?$")
for n, line in enumerate(open(path), 1):
    m = pat.match(line)
    if m:
        comment = (m.group(3) or "").strip()
        print(f"L{n:<4} {m.group(1):<42} = {m.group(2):<6} {comment}")
