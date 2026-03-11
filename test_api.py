#!/usr/bin/env python
"""快速测试 video-generator 所需的后端 API"""
import requests

BASE = "http://localhost:8000"  # 改成 8001 如果后端在 8001

def test():
    print("1. 测试 config.js ...")
    r = requests.get(f"{BASE}/config.js", timeout=5)
    ok = r.status_code == 200 and "API_BASE" in r.text
    print(f"   {'✓' if ok else '✗'} {r.status_code}")

    print("2. 测试 /api/generate (预期 422 缺少图片) ...")
    r = requests.post(f"{BASE}/api/generate", data={"model": "seedream-5.0-lite", "mode": "avatar"}, timeout=5)
    ok = r.status_code in (200, 422)  # 422 = 路由正常，缺参数
    print(f"   {'✓' if ok else '✗'} {r.status_code}")

    if ok:
        print("\n后端 API 正常，video-generator 可调用。")
    else:
        print("\n请确认：1) 后端已启动 (uvicorn main:app --port 8000)  2) config.js 中 API_BASE 与后端端口一致")

if __name__ == "__main__":
    test()
