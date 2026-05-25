#!/usr/bin/env python3
# coding: utf-8

import sys
import rospy
from kuavo_msgs.msg import gestureTask
from kuavo_msgs.srv import gestureExecute, gestureExecuteRequest

_GESTURE_ALIASES = {
    # release / open palm
    "松开五指": "palm-open",
    "五指张开": "palm-open",
    "张开手掌": "palm-open",
    "open-palm": "palm-open",
    "palm_open": "palm-open",
    "palmopen": "palm-open",
    # grip / thumbs up (common in this demo)
    "虎克提": "thumbs-up",
    "点赞": "thumbs-up",
    "thumbs_up": "thumbs-up",
}

def _normalize_gesture_name(name: str) -> str:
    name = (name or "").strip()
    return _GESTURE_ALIASES.get(name, name)

def execute_gesture(gesture_name, hand_side):
    service_name = 'gesture/execute'
    rospy.init_node('gesture_control_node', anonymous=True)
    
    try:
        rospy.wait_for_service(service_name, timeout=5.0)
        gesture_service = rospy.ServiceProxy(service_name, gestureExecute)
        request = gestureExecuteRequest()
        gesture_name = _normalize_gesture_name(gesture_name)
        if not gesture_name:
            print("Empty gesture_name after normalization")
            sys.exit(1)
        request.gestures = [gestureTask(gesture_name=gesture_name, hand_side=hand_side)]
        response = gesture_service(request)
        
        if response.success:
            print(f"Gesture '{gesture_name}' executed successfully on hand {hand_side}")
            sys.exit(0)
        else:
            print(f"Failed to execute gesture '{gesture_name}': {response.message}")
            sys.exit(1)
            
    except rospy.ServiceException as e:
        print(f"Service call failed: {e}")
        sys.exit(1)
    except rospy.ROSException as e:
        print(f"ROS error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 gesture_control.py <gesture_name> [hand_side]")
        print("Example: python3 gesture_control.py palm-open 1")
        print("Example: python3 gesture_control.py 松开五指 1")
        sys.exit(1)
    
    gesture_name = sys.argv[1]
    hand_side = int(sys.argv[2]) if len(sys.argv) >= 3 else 1
    execute_gesture(gesture_name, hand_side)