# -*- coding: utf-8 -*-
"""在线仓库自检：读取环境变量 HD_GH_TOKEN（不落盘），列出关键目录内容。

用法：$env:HD_GH_TOKEN='...'; python scripts/check_repo_online.py
"""
import json
import os
import urllib.request

TOKEN = os.environ.get("HD_GH_TOKEN", "").strip()
BASE = "https://api.github.com/repos/runming/HyperDesign2.0"


def get(path):
    headers = {"User-Agent": "hd-check", "X-GitHub-Api-Version": "2022-11-28"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(BASE + path, headers=headers)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())


def main():
    for path in ("/contents/", "/contents/docs", "/contents/docs/demo", "/contents/backend/app"):
        try:
            items = get(path)
            names = [i["name"] for i in items]
            print(f"{path}: {', '.join(names)}")
        except Exception as exc:
            print(f"{path}: ERR {exc}")


if __name__ == "__main__":
    main()
