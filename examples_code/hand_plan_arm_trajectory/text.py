#!/usr/bin/env python3
# coding: utf-8

import rospy
import math
import time
import os
import requests

from humanoid_plan_arm_trajectory.srv import (
    planArmTrajectoryCubicSpline,
    planArmTrajectoryCubicSplineRequest,
)
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from kuavo_msgs.srv import changeArmCtrlMode
from kuavo_msgs.msg import sensorsData
from kuavo_msgs.msg import gestureTask
from kuavo_msgs.srv import gestureExecute, gestureExecuteRequest

current_arm_joint_state = []


def deg_to_rad(deg):
    return math.radians(deg)


def sensors_data_callback(msg):
    global current_arm_joint_state
    current_arm_joint_state = msg.joint_data.joint_q[12:26]
    current_arm_joint_state = [round(pos, 2) for pos in current_arm_joint_state]


# 左手臂全程保持 0，右手臂使用新数据
# r_arm_pitch, r_arm_roll, r_arm_yaw, r_forearm_pitch, r_hand_yaw, r_hand_pitch, r_hand_roll
# -39.0,       0.0,        35.2,      -70.6,           -11.2,      -5.9,         45.9
positions = [
    [deg_to_rad(angle) for angle in [0, 0, 0, 0, 0, 0, 0,    0,    0,    0,     0,     0,    0,    0]],
    [deg_to_rad(angle) for angle in [0, 0, 0, 0, 0, 0, 0,  -39.0,  0.0,  35.2, -72.6, 0, 20, -3]],
    [deg_to_rad(angle) for angle in [0, 0, 0, 0, 0, 0, 0,  -39.0,  0.0,  35.2, -72.6, 0, 20, -3]],
    [deg_to_rad(angle) for angle in [0, 0, 0, 0, 0, 0, 0,  -39.0,  0.0,  35.2, -72.6, 0, 20, -3]],
    [deg_to_rad(angle) for angle in [0, 0, 0, 0, 0, 0, 0,    0,    0,    0,     0,     0,    0,    0]],
]

times = [3 + 7 * i for i in range(len(positions))]

joint_state = JointState()


def traj_callback(msg):
    global joint_state
    if len(msg.points) == 0:
        return
    point = msg.points[0]
    joint_state.name = [
        "l_arm_pitch",
        "l_arm_roll",
        "l_arm_yaw",
        "l_forearm_pitch",
        "l_hand_yaw",
        "l_hand_pitch",
        "l_hand_roll",
        "r_arm_pitch",
        "r_arm_roll",
        "r_arm_yaw",
        "r_forearm_pitch",
        "r_hand_yaw",
        "r_hand_pitch",
        "r_hand_roll",
    ]
    joint_state.position = [math.degrees(pos) for pos in point.positions[:14]]
    joint_state.velocity = [math.degrees(vel) for vel in point.velocities[:14]]
    joint_state.effort = [0] * 14


def call_change_arm_ctrl_mode_service(arm_ctrl_mode):
    service_name = "humanoid_change_arm_ctrl_mode"
    try:
        rospy.wait_for_service(service_name, timeout=0.5)
        srv = rospy.ServiceProxy(service_name, changeArmCtrlMode)
        srv(control_mode=arm_ctrl_mode)
        rospy.loginfo("arm ctrl mode 服务调用成功")
        return True
    except Exception as e:
        rospy.logerr(f"arm ctrl mode 服务调用失败: {e}")
        return False


def gesture_client(gesture_name, hand_side):
    service_name = "gesture/execute"
    rospy.wait_for_service(service_name)
    try:
        gesture_service = rospy.ServiceProxy(service_name, gestureExecute)
        request = gestureExecuteRequest()
        request.gestures = [gestureTask(gesture_name=gesture_name, hand_side=hand_side)]
        response = gesture_service(request)
        if response.success:
            rospy.loginfo(
                f"Gesture '{gesture_name}' executed successfully (hand_side={hand_side})."
            )
        else:
            rospy.logerr(
                f"Failed to execute gesture '{gesture_name}' (hand_side={hand_side}): {response.message}"
            )
        return response.success
    except rospy.ServiceException as e:
        rospy.logerr(f"Gesture service call failed: {e}")
        return False


def plan_arm_traj_cubicspline_demo():
    rospy.wait_for_service("/cubic_spline/plan_arm_trajectory")
    plan_srv = rospy.ServiceProxy(
        "/cubic_spline/plan_arm_trajectory", planArmTrajectoryCubicSpline
    )
    request = planArmTrajectoryCubicSplineRequest()
    joint_trajectory = JointTrajectory()
    for i in range(len(times)):
        joint_trajectory.points.append(JointTrajectoryPoint())
        joint_trajectory.points[-1].positions = positions[i]
        joint_trajectory.points[-1].time_from_start = rospy.Duration(times[i])
    request.joint_trajectory = joint_trajectory
    request.joint_trajectory.joint_names = [
        "l_arm_pitch",
        "l_arm_roll",
        "l_arm_yaw",
        "l_forearm_pitch",
        "l_hand_yaw",
        "l_hand_pitch",
        "l_hand_roll",
        "r_arm_pitch",
        "r_arm_roll",
        "r_arm_yaw",
        "r_forearm_pitch",
        "r_hand_yaw",
        "r_hand_pitch",
        "r_hand_roll",
    ]
    response = plan_srv(request)
    return response.success


# ─── 拍照触发（非阻塞，失败不影响运动）──────────────────────────────────────
PHOTO_SERVER = os.environ.get("PHOTO_SERVER", "http://127.0.0.1:8889")


def trigger_photo_session(count=10, delay_ms=1000, interval_ms=100):
    url = f"{PHOTO_SERVER}/session/start"
    payload = {
        "count": int(count),
        "delay_ms": int(delay_ms),
        "interval_ms": int(interval_ms),
        "client_ts": time.time(),
    }
    try:
        r = requests.post(url, json=payload, timeout=0.8)
        r.raise_for_status()
        data = r.json()
        if data.get("ok", False):
            rospy.loginfo(f"[photo] triggered session={data.get('session')}")
            return True
        rospy.logerr(f"[photo] trigger failed: {data}")
        return False
    except Exception as e:
        rospy.logerr(f"[photo] trigger exception: {e}")
        return False


# ─── 主函数 ──────────────────────────────────────────────────────────────────
def main():
    rospy.init_node("arm_traj_cubicspline_trigger_photo_nonblocking")

    rospy.Subscriber(
        "/cubic_spline/arm_traj",
        JointTrajectory,
        traj_callback,
        queue_size=1,
        tcp_nodelay=True,
    )
    kuavo_arm_traj_pub = rospy.Publisher(
        "/kuavo_arm_traj", JointState, queue_size=1, tcp_nodelay=True
    )
    rospy.Subscriber(
        "/sensors_data_raw",
        sensorsData,
        sensors_data_callback,
        queue_size=1,
        tcp_nodelay=True,
    )

    call_change_arm_ctrl_mode_service(2)

    rospy.loginfo("Waiting for current_arm_joint_state from /sensors_data_raw ...")
    while not rospy.is_shutdown() and len(current_arm_joint_state) == 0:
        rospy.sleep(0.01)

    # 插入当前位置为起点
    times.insert(0, 2.0)
    positions.insert(0, current_arm_joint_state)

    if len(times) < 4:
        rospy.logerr("轨迹点数量不足")
        return

    all_done_t = float(times[-1])
    exit_margin_s = 1.0
    exit_t = all_done_t + exit_margin_s

    second_motion_done_t = float(times[2])

    rospy.loginfo(f"触发拍照：    {second_motion_done_t:.1f}s")
    rospy.loginfo(f"轨迹最后时间：{all_done_t:.1f}s，计划退出：{exit_t:.1f}s（+{exit_margin_s:.1f}s）")

    if not plan_arm_traj_cubicspline_demo():
        rospy.logerr("手臂轨迹规划失败")
        return
    rospy.loginfo("手臂轨迹规划成功")

    while kuavo_arm_traj_pub.get_num_connections() == 0 and not rospy.is_shutdown():
        rospy.loginfo("Waiting for /kuavo_arm_traj subscriber...")
        rospy.sleep(0.1)

    traj_start = rospy.Time.now().to_sec()

    #right_gesture_name = "thumbs-up"  # 右手：点赞
    #gesture_client(right_gesture_name, hand_side=1)  # 右手立即开始手势

    photo_triggered = False

    rate = rospy.Rate(100)

    while not rospy.is_shutdown():
        if len(joint_state.position) != 0:
            kuavo_arm_traj_pub.publish(joint_state)

    

        elapsed = rospy.Time.now().to_sec() - traj_start

        # 第二个动作完成：触发手机连拍（非阻塞）
        if not photo_triggered and elapsed >= second_motion_done_t:
            rospy.loginfo(f"[photo] elapsed={elapsed:.1f}s 触发连拍")
            trigger_photo_session(count=10, delay_ms=1000, interval_ms=100)
            photo_triggered = True

        # 到"最后时间 + 余量"自动退出
        if elapsed >= exit_t:
            rospy.loginfo(f"[exit] elapsed={elapsed:.1f}s reached exit_t={exit_t:.1f}s -> shutdown.")
            break

        rate.sleep()

    # 退出前取消右手手势
    #rospy.loginfo("[gesture] 取消右手手势")
    #gesture_client("empty", hand_side=1)

    # 退出清理
    rospy.signal_shutdown("arm trajectory finished")
    rospy.sleep(0.1)


if __name__ == "__main__":
    main()