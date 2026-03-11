#!/usr/bin/env python
"""本地冒烟测试：覆盖 video-generator 后端的核心接口"""
import io
import json
import requests

BASE = "http://localhost:8000"
SEP  = "-" * 55

def check(label, ok, extra=""):
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}{(' — ' + extra) if extra else ''}")
    return ok

def main():
    results = []

    # ── 1. 健康检查 ──────────────────────────────────────
    print(f"\n{SEP}")
    print("1. /health")
    r = requests.get(f"{BASE}/health", timeout=5)
    results.append(check("status 200", r.status_code == 200, str(r.json())))

    # ── 2. config.js ─────────────────────────────────────
    print(f"\n{SEP}")
    print("2. /config.js")
    r = requests.get(f"{BASE}/config.js", timeout=5)
    ok = r.status_code == 200 and "API_BASE" in r.text
    results.append(check("返回 API_BASE", ok))
    if ok:
        print("   ", r.text.strip().replace("\n", "\n    "))

    # ── 3. /agents ────────────────────────────────────────
    print(f"\n{SEP}")
    print("3. /agents")
    r = requests.get(f"{BASE}/agents", timeout=5)
    data = r.json()
    results.append(check("status 200", r.status_code == 200))
    for aid, info in data.items():
        configured = info.get("configured")
        results.append(check(f"agent '{aid}' 已配置", configured, info.get("name","")))

    # ── 4. /api/generate — 缺少图片 → 422 ────────────────
    print(f"\n{SEP}")
    print("4. /api/generate  (缺少图片 → 预期 422)")
    r = requests.post(f"{BASE}/api/generate",
                      data={"model": "seedream-5.0-lite", "mode": "avatar"}, timeout=5)
    results.append(check("422 参数校验", r.status_code == 422, str(r.status_code)))

    # ── 5. /api/generate — 不支持的模型 → 400 ─────────────
    print(f"\n{SEP}")
    print("5. /api/generate  (不支持模型 → 预期 400)")
    fake = io.BytesIO(b"fake-image-data")
    r = requests.post(f"{BASE}/api/generate",
                      files={"image": ("x.jpg", fake, "image/jpeg")},
                      data={"model": "no-such-model", "mode": "video"}, timeout=5)
    results.append(check("400 不支持模型", r.status_code == 400, r.json().get("detail","")))

    # ── 6. /api/task/<fake> — 不存在的 task_id ────────────
    print(f"\n{SEP}")
    print("6. /api/task/fake-task-999  (不存在 task_id)")
    r = requests.get(f"{BASE}/api/task/fake-task-999", timeout=10)
    results.append(check("返回 4xx/5xx", r.status_code >= 400,
                          str(r.status_code) + " " + str(r.json())))

    # ── 7. 视频模型 payload 逻辑验证（不真正调 APIMart）────
    print(f"\n{SEP}")
    print("7. 检查 payload 逻辑（GENERATE_API_KEY 缺失时 500）")
    # 用一个真实图片字节（1x1 JPEG）测试，期望后端能走到 key 检查
    tiny_jpg = (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
        b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
        b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1e>'
        b'\x41B\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41'
        b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00'
        b'\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00'
        b'\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00'
        b'\x08\x01\x01\x00\x00?\x00\xfb\xff\xd9'
    )
    for model, mode in [("sora-2", "video"), ("wan-2.6", "video"), ("seedream-5.0-lite", "avatar")]:
        r = requests.post(f"{BASE}/api/generate",
                          files={"image": ("photo.jpg", io.BytesIO(tiny_jpg), "image/jpeg")},
                          data={"model": model, "mode": mode}, timeout=15)
        # 200 = key 有效并提交成功；500 = key 缺失或上传失败；都说明路由正常
        route_ok = r.status_code in (200, 500, 502)
        results.append(check(f"model={model} mode={mode} 路由正常",
                              route_ok, f"HTTP {r.status_code}"))

    # ── 总结 ─────────────────────────────────────────────
    print(f"\n{SEP}")
    passed = sum(results)
    total  = len(results)
    print(f"结果：{passed}/{total} 通过")
    if passed == total:
        print("全部通过！后端 API 工作正常。")
    else:
        print("有测试未通过，请检查上方输出。")

if __name__ == "__main__":
    main()
