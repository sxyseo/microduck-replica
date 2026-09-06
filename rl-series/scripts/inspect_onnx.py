"""打印 ONNX 策略的输入/输出形状 —— 验证 61 维 obs / 14 维 action 的硬证据。

用法:
    python scripts/inspect_onnx.py <policy.onnx> [更多.onnx ...]
"""

import sys

import onnx

for path in sys.argv[1:]:
    model = onnx.load(path)
    print(f"== {path}")
    for i in model.graph.input:
        dims = [d.dim_value or d.dim_param for d in i.type.tensor_type.shape.dim]
        print(f"  INPUT  {i.name} {dims}")
    for o in model.graph.output:
        dims = [d.dim_value or d.dim_param for d in o.type.tensor_type.shape.dim]
        print(f"  OUTPUT {o.name} {dims}")
