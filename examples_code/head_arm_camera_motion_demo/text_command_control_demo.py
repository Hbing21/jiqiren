#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import rospy
from kuavo_msgs.msg import armTargetPoses, robotHeadMotionData
from kuavo_msgs.srv import changeArmCtrlMode, changeArmCtrlModeRequest


ARM_MODE_SERVICES = ["/arm_traj_change_mode", "humanoid_change_arm_ctrl_mode"]


def set_arm_mode(control_mode):
    for service_name in ARM_MODE_SERVICES:
        try:
            rospy.wait_for_service(service_name, timeout=1.0)
            client = rospy.ServiceProxy(service_name, changeArmCtrlMode)
            client(changeArmCtrlModeRequest(control_mode=control_mode))
            rospy.loginfo("Arm mode=%d set by %s", control_mode, service_name)
            return True
        except (rospy.ROSException, rospy.ServiceException):
            continue
    rospy.logwarn("Arm mode service not available.")
    return False


class TextCommandController:
    def __init__(self):
        rospy.init_node("text_command_control_demo")
        self.arm_pub = rospy.Publisher("/kuavo_arm_target_poses", armTargetPoses, queue_size=10)
        self.head_pub = rospy.Publisher("/robot_head_motion_data", robotHeadMotionData, queue_size=10)

        self.head_yaw = 0.0
        self.head_pitch = 0.0
        self.arm_pose = [0.0] * 14

        self.head_step = 5.0
        self.arm_step = 8.0
        self.max_head_yaw = 30.0
        self.max_head_pitch = 25.0
        self.max_arm_pitch = 45.0

        rospy.sleep(0.5)
        set_arm_mode(2)
        self.publish_current_state(duration=1.2)

    def publish_current_state(self, duration=1.2):
        head_msg = robotHeadMotionData()
        head_msg.joint_data = [self.head_yaw, self.head_pitch]
        self.head_pub.publish(head_msg)

        arm_msg = armTargetPoses()
        arm_msg.times = [duration]
        arm_msg.values = self.arm_pose
        self.arm_pub.publish(arm_msg)

    def clamp(self, value, low, high):
        return max(low, min(high, value))

    def handle_command(self, cmd):
        # 头部指令
        if cmd in ["头抬高", "抬头"]:
            self.head_pitch = self.clamp(self.head_pitch + self.head_step, -self.max_head_pitch, self.max_head_pitch)
        elif cmd in ["头低下", "低头"]:
            self.head_pitch = self.clamp(self.head_pitch - self.head_step, -self.max_head_pitch, self.max_head_pitch)
        elif cmd in ["头左转", "向左看"]:
            self.head_yaw = self.clamp(self.head_yaw + self.head_step, -self.max_head_yaw, self.max_head_yaw)
        elif cmd in ["头右转", "向右看"]:
            self.head_yaw = self.clamp(self.head_yaw - self.head_step, -self.max_head_yaw, self.max_head_yaw)
        elif cmd in ["头回正", "看前方"]:
            self.head_yaw = 0.0
            self.head_pitch = 0.0

        # 手臂指令（双臂同步）
        elif cmd in ["手臂抬高", "双臂抬高"]:
            self.arm_pose[0] = self.clamp(self.arm_pose[0] + self.arm_step, -10.0, self.max_arm_pitch)
            self.arm_pose[7] = self.clamp(self.arm_pose[7] + self.arm_step, -10.0, self.max_arm_pitch)
        elif cmd in ["手臂放下", "双臂放下"]:
            self.arm_pose[0] = self.clamp(self.arm_pose[0] - self.arm_step, -10.0, self.max_arm_pitch)
            self.arm_pose[7] = self.clamp(self.arm_pose[7] - self.arm_step, -10.0, self.max_arm_pitch)
        elif cmd in ["左臂抬高"]:
            self.arm_pose[0] = self.clamp(self.arm_pose[0] + self.arm_step, -10.0, self.max_arm_pitch)
        elif cmd in ["右臂抬高"]:
            self.arm_pose[7] = self.clamp(self.arm_pose[7] + self.arm_step, -10.0, self.max_arm_pitch)
        elif cmd in ["左臂放下"]:
            self.arm_pose[0] = self.clamp(self.arm_pose[0] - self.arm_step, -10.0, self.max_arm_pitch)
        elif cmd in ["右臂放下"]:
            self.arm_pose[7] = self.clamp(self.arm_pose[7] - self.arm_step, -10.0, self.max_arm_pitch)
        elif cmd in ["手臂回中", "双臂回中"]:
            self.arm_pose = [0.0] * 14

        # 停止与退出
        elif cmd in ["停止", "急停", "停下"]:
            self.head_yaw = 0.0
            self.head_pitch = 0.0
            self.arm_pose = [0.0] * 14
            self.publish_current_state(duration=1.0)
            set_arm_mode(1)
            rospy.loginfo("已执行停止：头回正、手臂回中、手臂模式切回1。")
            return True
        elif cmd in ["退出", "q", "quit", "exit"]:
            self.head_yaw = 0.0
            self.head_pitch = 0.0
            self.arm_pose = [0.0] * 14
            self.publish_current_state(duration=1.0)
            set_arm_mode(1)
            rospy.signal_shutdown("User requested exit.")
            return True
        else:
            rospy.logwarn("不支持的命令: %s", cmd)
            return False

        self.publish_current_state(duration=1.2)
        rospy.loginfo(
            "执行成功 | 头(yaw=%.1f, pitch=%.1f) 手臂(l_pitch=%.1f, r_pitch=%.1f)",
            self.head_yaw,
            self.head_pitch,
            self.arm_pose[0],
            self.arm_pose[7],
        )
        return True

    def run(self):
        print("")
        print("可用指令：")
        print("  头抬高 / 头低下 / 头左转 / 头右转 / 头回正")
        print("  手臂抬高 / 手臂放下 / 左臂抬高 / 右臂抬高 / 左臂放下 / 右臂放下 / 手臂回中")
        print("  停止（回安全位） / 退出")
        print("")
        while not rospy.is_shutdown():
            try:
                cmd = input("请输入命令: ").strip()
            except (EOFError, KeyboardInterrupt):
                cmd = "退出"
            if not cmd:
                continue
            self.handle_command(cmd)


if __name__ == "__main__":
    controller = TextCommandController()
    controller.run()
