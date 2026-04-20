# 机器人代码示例库

包含机器人相关的代码示例，包括：
- 手势控制
- 手臂轨迹规划
- 头部和手臂运动控制
- 标签检测
- YOLO目标检测
- 数据记录
- 步骤控制

## 主要文件

### hand_plan_arm_trajectory
- `server1.py` - HTTP服务端，负责管理拍摄会话和照片存储
- `test1.py` - 机器人手臂控制脚本，负责规划和执行手臂运动

## 如何运行

### 启动服务器
```bash
python3 examples_code/hand_plan_arm_trajectory/server1.py
```

### 启动手臂控制
```bash
python3 examples_code/hand_plan_arm_trajectory/test1.py
```
