#!/usr/bin/env python3
"""
update_status.py — Agent Dashboard 상태 업데이트 스크립트

사용법:
  python3 update_status.py [agent_id] [status] [task]
  python3 update_status.py knox running "배포 파이프라인 구축 중"
  python3 update_status.py cael done "카피 v4.2 완성"
  python3 update_status.py quinn idle

상태값: running / done / idle
agent_id 목록: bilard, cael, quinn, dorian, mira, lyra, knox, rex

인자 없이 실행하면 git log만 갱신:
  python3 update_status.py
"""

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
STATUS_FILE = SCRIPT_DIR / "data" / "status.json"
FOURPILLARS_DIR = "/Users/bilard/Projects/fourpillars"

KST = timezone(timedelta(hours=9))


def get_git_log(n=5):
    """fourpillars 레포에서 최근 커밋 읽기"""
    try:
        result = subprocess.run(
            ["git", "-C", FOURPILLARS_DIR, "log", "--oneline", f"-{n}",
             "--format=%H|%s|%ai"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return []
        commits = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({
                    "hash": parts[0][:7],
                    "message": parts[1],
                    "time": parts[2].strip()
                })
        return commits
    except Exception as e:
        print(f"[warn] git log 읽기 실패: {e}", file=sys.stderr)
        return []


def load_status():
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATUS_FILE.exists():
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"agents": [], "recentLogs": [], "deployUrl": "https://fourpillars-eosin.vercel.app"}


def save_status(data):
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[ok] status.json 업데이트 완료 → {STATUS_FILE}")


def now_kst():
    return datetime.now(KST).isoformat(timespec="seconds")


def build_recent_logs(commits):
    """git 커밋 → recentLogs 포맷 변환 (bilard 귀속)"""
    logs = []
    for c in commits:
        logs.append({
            "agentId": "bilard",
            "agentName": "빌라드",
            "agentEmoji": "👑",
            "message": c["message"],
            "time": c["time"]
        })
    return logs


def main():
    args = sys.argv[1:]
    agent_id = args[0] if len(args) > 0 else None
    new_status = args[1] if len(args) > 1 else None
    new_task = args[2] if len(args) > 2 else None

    valid_statuses = {"running", "done", "idle"}
    if new_status and new_status not in valid_statuses:
        print(f"[error] 유효하지 않은 상태: '{new_status}'. 사용 가능: {valid_statuses}")
        sys.exit(1)

    data = load_status()

    # git log 갱신
    commits = get_git_log(10)
    if commits:
        data["recentLogs"] = build_recent_logs(commits[:5])
        # 최근 커밋을 bilard 에이전트에 반영
        latest = commits[0]
        for agent in data["agents"]:
            if agent["id"] == "bilard":
                agent["lastCommit"] = latest["message"]
                agent["lastCommitTime"] = latest["time"]
                break
        print(f"[info] 최근 커밋 {len(commits)}개 반영")

    # 에이전트 상태 업데이트
    if agent_id:
        found = False
        for agent in data["agents"]:
            if agent["id"] == agent_id:
                found = True
                if new_status:
                    agent["status"] = new_status
                if new_task is not None:
                    agent["currentTask"] = new_task if new_task else None
                elif new_status == "idle":
                    agent["currentTask"] = None
                print(f"[ok] {agent['emoji']} {agent['name']} → status={agent['status']}, task={agent['currentTask']}")
                break
        if not found:
            print(f"[error] 에이전트 '{agent_id}'를 찾을 수 없음")
            sys.exit(1)

    data["updatedAt"] = now_kst()
    save_status(data)


if __name__ == "__main__":
    main()
