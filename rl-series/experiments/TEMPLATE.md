# 实验记录模板

> 规则：一次实验只改一个变量。跑之前先把「假设」写好——预注册防事后诸葛。
> 所有字段都要填，跑失败了「最终结论」里如实写失败原因，失败记录比成功更值钱。

```text
实验名称：
代码 commit：（上游 microduck_rl 的 git hash，如 29e887e）
本地改动：（diff 或一句话，附 patch 文件路径）
修改参数：（文件:行号，改前 → 改后）
我的假设：（跑之前写！预期哪个指标朝哪个方向变、为什么）
训练命令：（完整可复制的一条命令）
机器与硬件：（如 Mac mini CPU / RTX 4090 + HF Jobs）
训练时长：
显存占用：（CPU 跑写"-"；GPU 记 nvidia-smi 峰值）
TensorBoard 变化：（五指标：Train/mean_reward、Episode_Termination/fell_over、
                  Metrics/twist/error_vel_xy、Metrics/twist/error_vel_yaw、Policy/mean_std）
对比图路径：
最终结论：（假设成立/不成立/50迭代无法区分，为什么）
下一步：
```

生成对比图的命令：

```bash
python scripts/plot_ab_compare.py --a <runA目录> --b <runB目录> \
  --label-a "<A含义>" --label-b "<B含义>" \
  --tags Train/mean_reward Episode_Termination/fell_over \
  --out assets/expXXX-对比.png
```
