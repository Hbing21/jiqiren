#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import rospy
from kuavo_msgs.msg import armTargetPoses, robotHeadMotionData
from kuavo_msgs.srv import changeArmCtrlMode, changeArmCtrlModeRequest
from std_srvs.srv import Trigger, TriggerResponse


ARM_MODE_SERVICES = ["/arm_traj_change_mode", "humanoid_change_arm_ctrl_mode"]


def set_arm_mode(control_mode):
    """Switch arm controller mode."""
    for service_name in ARM_MODE_SERVICES:
        try:
            rospy.wait_for_service(service_name, timeout=1.0)
            client = rospy.ServiceProxy(service_name, changeArmCtrlMode)
            req = changeArmCtrlModeRequest(control_mode=control_mode)
            response = client(req)
            if hasattr(response, "result") and not response.result:
                rospy.logwarn("%s returned failure: %s", service_name, response.message)
            else:
                rospy.loginfo("Arm mode=%d set by %s", control_mode, service_name)
            return True
        except (rospy.ROSException, rospy.ServiceException):
            continue

    rospy.logwarn("No arm mode service available, continue without mode switch.")
    return False


def publish_safe_stop_pose(arm_pub, head_pub):
    """Send one neutral command so robot can stop in safe pose."""
    head_msg = robotHeadMotionData()
    head_msg.joint_data = [0.0, 0.0]
    head_pub.publish(head_msg)

    arm_msg = armTargetPoses()
    arm_msg.times = [1.5]
    arm_msg.values = [0.0] * 14
    arm_pub.publish(arm_msg)
    rospy.loginfo("Published safe stop pose (head center + arm zero).")


def build_arm_waypoints():
    """
    14 joints order:
    l_arm_pitch, l_arm_roll, l_arm_yaw, l_forearm_pitch, l_hand_yaw, l_hand_pitch, l_hand_roll,
    r_arm_pitch, r_arm_roll, r_arm_yaw, r_forearm_pitch, r_hand_yaw, r_hand_pitch, r_hand_roll
    Unit: degree
    """
    return [
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [20, 5, 0, -35, 0, 0, 0, 15, -5, 0, -25, 0, 0, 0],
        [30, 10, -8, -55, 0, 0, 0, 20, -8, 8, -40, 0, 0, 0],
        [10, 0, 0, -20, 0, 0, 0, 10, 0, 0, -20, 0, 0, 0],
    ]


def publish_motion():
    rospy.init_node("head_arm_camera_motion_demo")

    arm_pub = rospy.Publisher("/kuavo_arm_target_poses", armTargetPoses, queue_size=10)
    head_pub = rospy.Publisher("/robot_head_motion_data", robotHeadMotionData, queue_size=10)
    stop_state = {"requested": False}

    def stop_service_cb(_req):
        stop_state["requested"] = True
        return TriggerResponse(success=True, message="Stop requested, exiting motion loop.")

    rospy.Service("/head_arm_camera_motion_demo/stop", Trigger, stop_service_cb)

    # Give ROS time to establish publisher connections.
    rospy.sleep(0.5)
    set_arm_mode(2)

    arm_waypoints = build_arm_waypoints()
    waypoint_duration = 1.8  # seconds
    head_yaw_amp = 22.0
    head_pitch_amp = 12.0
    head_freq_hz = 0.12

    rate = rospy.Rate(20)
    start_t = rospy.Time.now().to_sec()
    last_waypoint_idx = -1

    rospy.loginfo("Start publishing arm/head motion. Press Ctrl+C to stop.")
    while not rospy.is_shutdown() and not stop_state["requested"]:
        now = rospy.Time.now().to_sec() - start_t

        # 1) Head periodic motion, so camera view moves smoothly.
        head_msg = robotHeadMotionData()
        head_yaw = head_yaw_amp * math.sin(2.0 * math.pi * head_freq_hz * now)
        head_pitch = head_pitch_amp * math.sin(2.0 * math.pi * head_freq_hz * now + math.pi / 2.0)
        head_msg.joint_data = [head_yaw, head_pitch]
        head_pub.publish(head_msg)

        # 2) Arm waypoint loop. Publish only when switching waypoint.
        waypoint_idx = int(now / waypoint_duration) % len(arm_waypoints)
        if waypoint_idx != last_waypoint_idx:
            arm_msg = armTargetPoses()
            arm_msg.times = [waypoint_duration]
            arm_msg.values = arm_waypoints[waypoint_idx]
            arm_pub.publish(arm_msg)
            last_waypoint_idx = waypoint_idx
            rospy.loginfo("Published arm waypoint index: %d", waypoint_idx)

        rate.sleep()

    publish_safe_stop_pose(arm_pub, head_pub)
    set_arm_mode(1)
    rospy.loginfo("Motion stopped.")


if __name__ == "__main__":
    try:
        publish_motion()
    except rospy.ROSInterruptException:
        pass
