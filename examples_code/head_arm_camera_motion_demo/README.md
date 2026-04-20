# 头部+手臂联动示例（带动摄像头视角）

该目录是独立新增示例，不会修改原有 `LAB` 代码。

## 文件位置

`/home/lab/kuavo-ros-opensource/src/demo/examples_code/head_arm_camera_motion_demo`

## 脚本说明

- `head_arm_camera_motion_demo.py`
  - 发布头部控制话题：`/robot_head_motion_data`
  - 发布手臂目标话题：`/kuavo_arm_target_poses`
  - 尝试调用手臂模式服务（外部控制模式）：`/arm_traj_change_mode`（失败时自动尝试 `humanoid_change_arm_ctrl_mode`）
- `text_command_control_demo.py`
  - 终端输入中文命令控制头部和手臂
  - 支持：`头抬高`、`头低下`、`头左转`、`头右转`、`头回正`
  - 支持：`手臂抬高`、`手臂放下`、`左臂抬高`、`右臂抬高`、`手臂回中`
  - 支持：`停止`（回安全位并切回模式1）、`退出`
- `voice_command_control_demo.py`
  - 麦克风语音识别中文指令并控制机器人
  - 识别后自动映射到文本命令（例如“抬头”->`头抬高`）
  - 支持命令：`头抬高`、`头低下`、`头左转`、`头右转`、`头回正`、`手臂抬高`、`手臂放下`、`左臂抬高`、`右臂抬高`、`停止`、`退出`

## 运行步骤

1) 启动机器人控制相关节点（仿真或实机，保持你当前已有流程即可）

2) 新开终端执行：

```bash
cd /home/lab/kuavo-ros-opensource
source devel/setup.bash
python3 src/demo/examples_code/head_arm_camera_motion_demo/head_arm_camera_motion_demo.py
```

### 文本命令控制模式（推荐你当前需求）

```bash
cd /home/lab/kuavo-ros-opensource
source devel/setup.bash
python3 src/demo/examples_code/head_arm_camera_motion_demo/text_command_control_demo.py
```

运行后在终端直接输入中文命令并回车，例如：

- `头抬高`
- `头左转`
- `手臂抬高`
- `停止`

### 语音识别控制模式（麦克风）

先安装依赖（仅首次）：

```bash
pip3 install SpeechRecognition pyaudio
```

运行语音控制：

```bash
cd /home/lab/kuavo-ros-opensource
source devel/setup.bash
python3 src/demo/examples_code/head_arm_camera_motion_demo/voice_command_control_demo.py
```

运行后按提示对着麦克风说：

- `头抬高`
- `头左转`
- `手臂抬高`
- `停止`
- `退出`

## 可调参数（在脚本里改）

- `waypoint_duration`：手臂每个姿态停留时长
- `head_yaw_amp`：头部 yaw 振幅（建议 <= 25 度）
- `head_pitch_amp`：头部 pitch 振幅（建议 <= 15 度）
- `head_freq_hz`：头部摆动频率

## 安全建议

- 实机调试先将振幅设小，再逐步增大。
- 机器人站立状态下测试时建议有人保护。
