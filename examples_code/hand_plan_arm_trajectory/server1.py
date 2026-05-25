#!/usr/bin/env python3
"""
拍照机器人 HTTP 服务端 v2
运行：python3 server1.py

接口：
  POST /arm/start       → 用户 App 调用：启动手臂触发脚本 test1.py（非阻塞）
  GET  /arm/status      → 查询 test1.py 是否仍在运行
  POST /gesture/release → 立即执行“松开五指/张开手掌”手势
  POST /session/start   → test1.py 调用，触发手机连拍
  GET  /session/status  → 设备端 App 轮询，获取当前拍摄状态
  POST /upload/<session>/<filename>  → 设备端 App 上传照片到机器人
  GET  /photos          → 返回最新 session 照片列表
  GET  /photos/<session>/<file>      → 返回图片文件
"""

import subprocess, os, json, mimetypes, time, threading, signal, sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# ─── 配置 ─────────────────────────────────────────────────────────────────────
PORT       = 8021

# 用户 App 触发的脚本：手臂动作触发节点（绝对路径）
TEST1_PY    = "/home/lab/kuavo-ros-opensource/src/demo/examples_code/hand_plan_arm_trajectory/test1.py"

# 手势控制脚本路径
GESTURE_CTRL_PY = "/home/lab/kuavo-ros-opensource/src/demo/examples_code/hand_plan_arm_trajectory/gesture_control.py"

# 8021 端原始图片存放（持久目录，避免 /tmp 重启清空）
# 8022 端会再通过 /api/capture/sessions/{id}/import-from-robot 拷贝到归属用户的目录
PHOTO_BASE = os.environ.get("PHOTO_BASE", "/home/lab/robot_photos_raw")

# 右手握持手势配置
GRIP_GESTURE = os.environ.get("GRIP_GESTURE", "thumbs-up")  # 虎克提手势
GRIP_HAND_SIDE = 1                                          # 右手
RELEASE_GRIP_ON_EXIT = os.environ.get("RELEASE_GRIP_ON_EXIT", "1") == "1"
RELEASE_GESTURE = os.environ.get("RELEASE_GESTURE", "palm-open")   # 五指张开

_server = None

def execute_gesture(gesture_name, hand_side):
    """执行手势控制"""
    try:
        env = os.environ.copy()
        devel_py = "/home/lab/kuavo-ros-opensource/devel/lib/python3/dist-packages"
        env["PYTHONPATH"] = f"{devel_py}:{env.get('PYTHONPATH', '')}"
        result = subprocess.run(
            ["python3", GESTURE_CTRL_PY, gesture_name, str(hand_side)],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        if result.returncode == 0:
            print(f"[gesture] 成功执行手势 '{gesture_name}' (hand_side={hand_side})")
            return True
        else:
            print(f"[gesture] 执行手势失败 '{gesture_name}': {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print(f"[gesture] 执行手势超时 '{gesture_name}'")
        return False
    except Exception as e:
        print(f"[gesture] 执行手势异常 '{gesture_name}': {e}")
        return False


def ensure_startup_grip(max_retry=10, retry_interval_s=0.5):
    """启动阶段确保右手握持手势设置成功。"""
    for i in range(1, max_retry + 1):
        if execute_gesture(GRIP_GESTURE, GRIP_HAND_SIDE):
            print(f"[gesture] 右手握持手势已就绪（第 {i} 次尝试成功）")
            return True
        print(f"[gesture] 启动握持手势失败，{retry_interval_s:.1f}s 后重试 ({i}/{max_retry})")
        time.sleep(retry_interval_s)
    return False

def signal_handler(signum, frame):
    """信号处理：关闭服务时取消手势"""
    print(f"\n[exit] 收到信号 {signum}，准备关闭服务...")
    
    # 默认不松开右手，避免拍摄设备掉落；如需松开可设置 RELEASE_GRIP_ON_EXIT=1
    if RELEASE_GRIP_ON_EXIT:
        print(f"[gesture] 结束时释放手势 -> '{RELEASE_GESTURE}'")
        execute_gesture(RELEASE_GESTURE, GRIP_HAND_SIDE)
    else:
        print("[gesture] 保持右手握持手势（未执行 empty）")
    
    # 关闭 HTTP 服务器
    if _server:
        _server.shutdown()
    
    print("[exit] 服务已关闭")
    sys.exit(0)

# ─────────────────────────────────────────────────────────────────────────────

# 全局拍摄状态
_session_lock   = threading.Lock()
_session_state  = {
    "status":      "idle",   # idle | pending | shooting | done
    "session":     "",
    "count":       6,
    "delay_ms":    1000,
    "interval_ms": 200,
    "triggered_at": 0.0,
}

# 手臂触发脚本进程（test1.py）
_arm_lock = threading.Lock()
_arm_proc = None  # subprocess.Popen

def _new_session_id():
    return time.strftime("%Y%m%d_%H%M%S")

class Handler(BaseHTTPRequestHandler):

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    # ── GET ───────────────────────────────────────────────────────────────────
    def do_GET(self):
        p = self.path.split("?")[0]

        if p == "/ping":
            self._send_json(200, {"ok": True, "msg": "机器人在线"})

        elif p == "/session/status":
            with _session_lock:
                self._send_json(200, {"ok": True, **dict(_session_state)})

        elif p == "/arm/status":
            global _arm_proc
            with _arm_lock:
                running = _arm_proc is not None and (_arm_proc.poll() is None)
                pid = _arm_proc.pid if _arm_proc is not None else 0
            self._send_json(200, {"ok": True, "running": running, "pid": pid})

        elif p == "/photos":
            self._serve_photo_list()

        elif p.startswith("/photos/"):
            self._serve_photo_file(p[len("/photos/"):])

        else:
            self._send_json(404, {"ok": False, "msg": "未知接口"})

    # ── POST ──────────────────────────────────────────────────────────────────
    def do_POST(self):
        p = self.path.split("?")[0]

        # 用户 App：启动手臂触发脚本 test1.py（非阻塞）
        if p == "/arm/start":
            self._arm_start()

        # 立即执行“松开五指/张开手掌”手势
        elif p == "/gesture/release":
            ok = execute_gesture(RELEASE_GESTURE, GRIP_HAND_SIDE)
            self._send_json(200, {"ok": bool(ok), "gesture": RELEASE_GESTURE, "hand_side": GRIP_HAND_SIDE})

        # test1.py 调用：触发设备端连拍（创建session）
        elif p == "/session/start":
            try:
                body = json.loads(self._read_body() or b"{}")
            except Exception:
                body = {}

            sid = _new_session_id()
            os.makedirs(os.path.join(PHOTO_BASE, sid), exist_ok=True)

            with _session_lock:
                _session_state.update({
                    "status":       "pending",
                    "session":      sid,
                    "count":        int(body.get("count",       6)),
                    "delay_ms":     int(body.get("delay_ms",    1000)),
                    "interval_ms":  int(body.get("interval_ms", 200)),
                    "triggered_at": time.time(),
                })

            print(f"[session] 新拍摄任务 session={sid} count={_session_state['count']}")
            self._send_json(200, {"ok": True, "session": sid})

        # 设备端 App 上传照片：POST /upload/<session>/<filename>
        elif p.startswith("/upload/"):
            parts = p[len("/upload/"):].split("/", 1)
            if len(parts) == 2:
                sid, fname = parts
                if ".." in sid or ".." in fname:
                    self._send_json(403, {"ok": False, "msg": "非法路径"}); return

                save_dir = os.path.join(PHOTO_BASE, sid)
                os.makedirs(save_dir, exist_ok=True)

                data = self._read_body()
                with open(os.path.join(save_dir, fname), "wb") as f:
                    f.write(data)

                print(f"[upload] {sid}/{fname}  {len(data)} bytes")

                # 更新状态（基于目录内图片数量）
                with _session_lock:
                    if _session_state["session"] == sid:
                        uploaded = len([
                            x for x in os.listdir(save_dir)
                            if x.lower().endswith((".jpg",".jpeg",".png"))
                        ])
                        if uploaded >= _session_state["count"]:
                            _session_state["status"] = "done"
                        else:
                            _session_state["status"] = "shooting"

                self._send_json(200, {"ok": True})
            else:
                self._send_json(400, {"ok": False, "msg": "路径格式错误"})

        else:
            self._send_json(404, {"ok": False, "msg": "未知接口"})

    def _arm_start(self):
        """
        启动 test1.py（非阻塞）。
        - 防止重复启动：如果仍在运行，直接返回 running=true
        - 用 python3 直接运行脚本；确保脚本内部环境（ROS等）可用
        """
        global _arm_proc
        if not os.path.isfile(TEST1_PY):
            self._send_json(500, {"ok": False, "msg": f"test1.py 不存在：{TEST1_PY}"})
            return

        with _arm_lock:
            if _arm_proc is not None and (_arm_proc.poll() is None):
                self._send_json(200, {"ok": True, "running": True, "pid": _arm_proc.pid, "msg": "test1.py 已在运行"})
                return

            # 启动进程（不阻塞HTTP）
            # 确保 ROS 环境变量被正确设置
            env = os.environ.copy()
            env['PYTHONPATH'] = '/home/lab/kuavo-ros-opensource/devel/lib/python3/dist-packages:' + env.get('PYTHONPATH', '')
            env['ROS_DISTRO'] = 'noetic'
            env['ROS_ROOT'] = '/opt/ros/noetic/share/ros'
            
            # 尝试创建日志目录（如果权限不足则忽略）
            try:
                os.makedirs(os.path.expanduser('~/.ros/log'), exist_ok=True)
            except PermissionError:
                print("[arm] 警告: 无法创建日志目录，可能会影响ROS日志记录")
            
            # 启动 test1.py
            # 注意：必须避免使用未读取的 PIPE，否则 ROS 日志写满缓冲区后会卡住子进程
            try:
                log_dir = "/home/lab/robot_user_backend/logs"
                os.makedirs(log_dir, exist_ok=True)
                log_path = os.path.join(log_dir, f"test1_{time.strftime('%Y%m%d_%H%M%S')}.log")
                arm_log = open(log_path, "ab", buffering=0)
                _arm_proc = subprocess.Popen(
                    ["python3", TEST1_PY],
                    stdout=arm_log,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
                print(f"[arm] log -> {log_path}")
            except Exception as log_err:
                print(f"[arm] 日志重定向失败({log_err})，回退到 DEVNULL")
                _arm_proc = subprocess.Popen(
                    ["python3", TEST1_PY],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=env,
                )
            pid = _arm_proc.pid

        print(f"[arm] started test1.py pid={pid} path={TEST1_PY}")
        self._send_json(200, {"ok": True, "running": True, "pid": pid, "msg": "已启动手臂触发脚本"})

    # ── 照片列表 ──────────────────────────────────────────────────────────────
    def _serve_photo_list(self):
        try:
            if not os.path.exists(PHOTO_BASE):
                self._send_json(200, {"ok": True, "session": "", "photos": []}); return
            sessions = sorted([
                d for d in os.listdir(PHOTO_BASE)
                if os.path.isdir(os.path.join(PHOTO_BASE, d))
            ], reverse=True)
            if not sessions:
                self._send_json(200, {"ok": True, "session": "", "photos": []}); return
            # 优先返回「当前会话」目录：避免设备闪退后再次拍照产生新目录时，
            # 客户端只看「字典序最新」而误认为上一轮照片「被清空」（其实仍在磁盘旧目录下）。
            with _session_lock:
                active = (_session_state.get("session") or "").strip()
            if active and os.path.isdir(os.path.join(PHOTO_BASE, active)):
                latest = active
            else:
                latest = sessions[0]
            sdir   = os.path.join(PHOTO_BASE, latest)
            photos = [
                {"name": f, "url": f"/photos/{latest}/{f}"}
                for f in sorted(os.listdir(sdir))
                if f.lower().endswith((".jpg",".jpeg",".png"))
            ]
            self._send_json(200, {"ok": True, "session": latest, "photos": photos})
        except Exception as e:
            self._send_json(500, {"ok": False, "msg": str(e)})

    # ── 图片文件 ──────────────────────────────────────────────────────────────
    def _serve_photo_file(self, rel):
        parts = rel.split("/", 1)
        if len(parts) != 2:
            self._send_json(404, {"ok": False, "msg": "路径错误"}); return
        sid, fname = parts
        if ".." in sid or ".." in fname:
            self._send_json(403, {"ok": False, "msg": "非法路径"}); return
        fp = os.path.join(PHOTO_BASE, sid, fname)
        if not os.path.isfile(fp):
            self._send_json(404, {"ok": False, "msg": "文件不存在"}); return
        mime = mimetypes.guess_type(fname)[0] or "application/octet-stream"
        with open(fp, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type",   mime)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")


if __name__ == "__main__":
    os.makedirs(PHOTO_BASE, exist_ok=True)
    
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print(f"╔══════════════════════════════════════╗")
    print(f"║  拍照机器人服务端 v2  端口:{PORT}      ║")
    print(f"║  照片目录: {PHOTO_BASE}  ║")
    print(f"║  test1.py:  {TEST1_PY}  ║")
    print(f"╚══════════════════════════════════════╝")
    
    _server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    _server.serve_forever()
