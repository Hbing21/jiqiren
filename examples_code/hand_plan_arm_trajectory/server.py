#!/usr/bin/env python3
"""
拍照机器人 HTTP 服务端 v2
运行：python3 server.py

新增接口：
  POST /session/start   → text.py 调用，触发手机连拍
  GET  /session/status  → 设备端 App 轮询，获取当前拍摄状态
  POST /upload/<session>/<filename>  → 设备端 App 上传照片到机器人
  GET  /photos          → 返回最新 session 照片列表
  GET  /photos/<session>/<file>      → 返回图片文件

新增（本次）：
  POST /arm/start       → 用户 App 调用：启动手臂触发���本 text.py（非阻塞）
  GET  /arm/status      → 查询 text.py 是否仍在运行
"""

import subprocess, os, json, mimetypes, time, threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ─── 配置 ─────────────────────────────────────────────────────────────────────
PORT       = 8889

# 兼容旧接口 /shoot：执行 test.py（如果你还在用）
TEST_PY    = os.path.expanduser(
    "~/kuavo-ros-opensource/src/demo/examples_code/hand_plan_arm_trajectory/test.py"
)

# 用户 App 触发的脚本：手臂动作触发节点（你给的绝对路径）
TEXT_PY    = "/home/lab/kuavo-ros-opensource/src/demo/examples_code/hand_plan_arm_trajectory/text.py"

PHOTO_BASE = "/tmp/robot_photos"
# ─────────────────────────────────────────────────────────────────────────────

# 全局拍摄状态
_session_lock   = threading.Lock()
_session_state  = {
    "status":      "idle",   # idle | pending | shooting | done
    "session":     "",
    "count":       10,
    "delay_ms":    1000,
    "interval_ms": 200,
    "triggered_at": 0.0,
}

# 手臂触发脚本进程（text.py）
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

        # 用户 App：启动手臂触发脚本 text.py（非阻塞）
        if p == "/arm/start":
            self._arm_start()

        # text.py 调用：触发设备端连拍（创建session）
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
                    "count":        int(body.get("count",       10)),
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

        # /shoot → 执行 test.py（兼容旧接口）
        elif p == "/shoot":
            print(f"[shoot] 执行 {TEST_PY}")
            try:
                result = subprocess.run(["python3", TEST_PY],
                                        capture_output=True, text=True)
                if result.returncode == 0:
                    self._send_json(200, {"ok": True,  "msg": "拍摄成功"})
                else:
                    self._send_json(200, {"ok": False, "msg": result.stderr.strip()})
            except Exception as e:
                self._send_json(500, {"ok": False, "msg": str(e)})

        else:
            self._send_json(404, {"ok": False, "msg": "未知接口"})

    def _arm_start(self):
        """
        启动 text.py（非阻塞）。
        - 防止重复启动：如果仍在运行，直接返回 running=true
        - 用 python3 直接运行脚本；确保脚本内部环境（ROS等）可用
        """
        global _arm_proc
        if not os.path.isfile(TEXT_PY):
            self._send_json(500, {"ok": False, "msg": f"text.py 不存在：{TEXT_PY}"})
            return

        with _arm_lock:
            if _arm_proc is not None and (_arm_proc.poll() is None):
                self._send_json(200, {"ok": True, "running": True, "pid": _arm_proc.pid, "msg": "text.py 已在运行"})
                return

            # 启动进程（不阻塞HTTP）
            # 注意：如果你的 ROS 环境变量需要 source，这里可能需要改成 bash -lc "source ... && python3 ..."
            _arm_proc = subprocess.Popen(
                ["python3", TEXT_PY],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            pid = _arm_proc.pid

        print(f"[arm] started text.py pid={pid} path={TEXT_PY}")
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
    print(f"╔══════════════════════════════════════╗")
    print(f"║  拍照机器人服务端 v2  端口:{PORT}      ║")
    print(f"║  照片目录: {PHOTO_BASE}  ║")
    print(f"║  text.py:  {TEXT_PY}  ║")
    print(f"╚══════════════════════════════════════╝")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()