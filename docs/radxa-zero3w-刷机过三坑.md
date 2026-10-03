# Radxa Zero 3W 刷机过三坑（走路冲刺 S1 执行手册）

> 目标：把 SD 卡插进电脑之前，本文没有需要临场决策的东西；插卡之后，每一步都带
> 「怎么验证做成了」。三坑的**修复**不用手工——官方
> `pollen-robotics/microduck` 的 `scripts/setup-board.sh` / `scripts/setup-npu.sh`
> 已经自动化（本仓库 `upstream/microduck/` checkout 可直接核对）；本文负责：
> 镜像就位 → 烧录 → 首启 → 跑官方 provision → 逐坑验收。
> 写作依据：upstream `deploy/README.md` + `scripts/`（2026-10 本地副本，行号可查）。

## 0. 镜像（已下载就位）

| 项 | 值 |
|---|---|
| 镜像 | **Armbian 26.8.1 Minimal**（Debian 13 trixie，**vendor 内核 6.1.115**——RKNN NPU 驱动在 vendor 内核里，别换 mainline 内核） |
| 本地路径 | `~/Downloads/radxa-zero3w/Armbian-radxa-zero3-trixie-minimal.img.xz` |
| sha256 | `e78de9cb4b2d8ff1710c65c509d08faef1ba88c07fc3276b9dd637597e8234e8` |
| 校验 | `shasum -a 256 ~/Downloads/radxa-zero3w/Armbian-radxa-zero3-trixie-minimal.img.xz`（对照官方 `https://dl.armbian.com/radxa-zero3/Trixie_vendor_minimal.sha`） |
| 来源 | `https://dl.armbian.com/radxa-zero3/Trixie_vendor_minimal`（该板已不供 bookworm，trixie 为现行稳定；26.8.1 修复了 Zero 3 蓝牙） |

## 1. 烧录（macOS）

1. 插 SD 卡（≥16GB，A1/A2 级），`diskutil list` 认准**外置 physical** 磁盘号——别烧错盘。
2. 烧录（二选一）：
   - **图形**：Raspberry Pi Imager，直接选 `.img.xz`（自动解压校验）；
   - **命令行**：
     ```bash
     diskutil unmountDisk diskN
     xz -dk Armbian_26.8.1_Radxa-zero3_trixie_vendor_6.1.115_minimal.img.xz
     sudo dd if=Armbian_26.8.1_Radxa-zero3_trixie_vendor_6.1.115_minimal.img \
             of=/dev/rdiskN bs=4m oflag=sync
     diskutil eject diskN
     ```
3. 不需要接串口调试线：刷完靠 ssh。

## 2. 首启

1. 上电（5V USB-C），等 3–5 分钟（首次扩容文件系统），`arp -a` 或路由器后台找 IP；
2. `ssh root@<IP>`（默认密码 `1234`，强制定新密码；顺手建普通用户）；
3. Armbian minimal 出厂是 netplan + systemd-networkd——**不用手动动它**，官方
   `migrate-network.sh` 会切到 NetworkManager（这是三坑之外的第四坑，官方脚本自动过；
   不切的话 `robotctl net status` 永远 Unavailable）。

## 3. 官方 provision（三坑在脚本里自动修）

按 `upstream/microduck/deploy/README.md`，板上执行：

```bash
DUCK_TOKEN=<github token> bash provision.sh
```

或站在 Mac 上跑 `scripts/provision-board.sh`（等板子出现、流式打日志、收尾给健康报告）。
流程：`setup-board.sh` → `migrate-network.sh` → 重启 → 两个再跑 → `install.sh`。
（脚本从 github.com/pollen-robotics/microduck 拉取；仓库公开，token 只有私有资产和
后续更新器 updaterd 用。）

## 4. 三坑逐个验收（每坑一条「证明它修好了」的命令）

| 坑 | 谁修的 | 验收 | 通过标准 |
|---|---|---|---|
| ① `serial-getty@ttyS2` 登录控制台占着舵机串口 | `setup-board.sh`（mask 单元 + 内核 `console=ttyS2` 处理，scripts/setup-board.sh L377–401） | `systemctl status serial-getty@ttyS2`；`fuser -v /dev/ttyS2`（Pollen 的查法） | masked/不存在；fuser 无进程——`/dev/ttyS2` 空闲让给 robotd |
| ②a `overlay_prefix=rk35xx` 加载不到任何 overlay（RK3566 与 RK3568 共用 `rk3568-*.dtbo`，前缀错则静默失效、板子照常启动） | `setup-board.sh` L244–249（直接 sed 改 `/boot/armbianEnv.txt`，`armbian-config` 的 overlay 编辑器在同因下会崩） | `grep overlay_prefix /boot/armbianEnv.txt` | `rk3568`，且 ②b 的 overlay 真能加载（见下） |
| ②b i2c3 抢脚：排针 3/5 脚硬件 I²C（IMU/ToF 传感总线） | `overlays=i2c3-pihat`（setup-board.sh 音频段；`deploy/audio/i2c3-pihat.dts`——3/5 脚硬件 i2c3） | `ls /dev/i2c-*`；`i2cdetect -y <n>` | 总线出现、可扫描。**代价：失去 USB-C PD 协商（5V 充电仍可用）** |
| ③ NPU 出厂禁用 | `setup-npu.sh`（装 `librknnrt.so` runtime + `overlays=` 追加 `npu-enable`，`deploy/overlays/rk3568-npu-enable.dts`） | `grep overlays /boot/armbianEnv.txt` 含 `npu-enable`；脚本输出内核驱动版本 | **走路不需要 NPU**（ONNX 跑 CPU）——此项可后置到 duck_detect 需要时 |

⚠ 官方 README 明说的复发条件：`apt upgrade` 若重指 `/boot/{Image,dtb,uInitrd}`，坑②会
复发——板子突然看不到舵机，先重跑 `setup-board.sh` 再怀疑别的。

## 5. 刷机完成的定义（G3 前置自检）

- [ ] ssh 稳定；wifi 归 NetworkManager 管（`robotctl net status` 非 Unavailable）
- [ ] `/dev/ttyS2` 存在且空闲（坑①验收过）
- [ ] `overlays=` 含 `i2c3-pihat`（NPU 可后置）
- [ ] `install.sh` 装完 daemon，健康检查通过（provision-board.sh 收尾报告）
- 之后：40pin 的 UART2（8/10 脚）接 `imu_to_dxl`——半双工 1Mbps 8N1，
  板上 SN74LVC1G126 做方向切换；整机联调见走路冲刺表 S7（`复刻关键路径-30天.md`）。
