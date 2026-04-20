#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Voice command demo for kuavo head/arm control.

Dependency:
    pip3 install SpeechRecognition pyaudio

Usage:
    python3 voice_command_control_demo.py
"""

import re
import rospy

try:
    import speech_recognition as sr
except ImportError:
    sr = None

from text_command_control_demo import TextCommandController


ALIASES = {
    "抬头": "头抬高",
    "头抬高": "头抬高",
    "抬高头": "头抬高",
    "低头": "头低下",
    "头低下": "头低下",
    "头左转": "头左转",
    "向左看": "头左转",
    "头右转": "头右转",
    "向右看": "头右转",
    "头回正": "头回正",
    "看前方": "头回正",
    "手臂抬高": "手臂抬高",
    "双臂抬高": "手臂抬高",
    "手臂放下": "手臂放下",
    "双臂放下": "手臂放下",
    "左臂抬高": "左臂抬高",
    "右臂抬高": "右臂抬高",
    "左臂放下": "左臂放下",
    "右臂放下": "右臂放下",
    "手臂回中": "手臂回中",
    "双臂回中": "手臂回中",
    "停止": "停止",
    "停下": "停止",
    "急停": "停止",
    "退出": "退出",
}


def normalize_text(text):
    """Normalize speech text to a supported command."""
    raw = text.strip().replace(" ", "")
    raw = re.sub(r"[，。！？、,.!?]", "", raw)
    for key, command in ALIASES.items():
        if key in raw:
            return command
    return ""


def main():
    if sr is None:
        print("缺少依赖：SpeechRecognition。")
        print("请先执行: pip3 install SpeechRecognition pyaudio")
        return

    controller = TextCommandController()
    recognizer = sr.Recognizer()

    try:
        mic = sr.Microphone()
    except OSError as exc:
        print("无法打开麦克风:", exc)
        print("请检查麦克风设备后重试。")
        return

    print("")
    print("语音控制已启动。")
    print("说出命令示例：头抬高 / 手臂抬高 / 头左转 / 停止 / 退出")
    print("如果识别不稳定，可以再说慢一点、靠近麦克风。")
    print("")

    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=1.0)

    while not rospy.is_shutdown():
        try:
            with mic as source:
                print("请说指令...")
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=3)

            # zh-CN for Chinese recognition
            text = recognizer.recognize_google(audio, language="zh-CN")
            print("识别结果:", text)

            cmd = normalize_text(text)
            if not cmd:
                print("未匹配到支持指令，请重试。")
                continue

            controller.handle_command(cmd)
            if cmd == "退出":
                break

        except sr.WaitTimeoutError:
            print("等待语音超时，继续监听...")
        except sr.UnknownValueError:
            print("未听清，请重试。")
        except sr.RequestError as exc:
            print("语音识别服务请求失败:", exc)
            print("请检查网络，或切换到文本命令脚本。")
        except KeyboardInterrupt:
            controller.handle_command("退出")
            break


if __name__ == "__main__":
    main()
