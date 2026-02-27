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

Next Up / Queue 관리:
  python3 update_status.py --next-task '{"agentId":"cael","agentName":"케일","task":"작업명","eta":"5분"}'
  python3 update_status.py --next-task null
  python3 update_status.py --queue-add '{"order":1,"agentId":"quinn","agentName":"퀸","task":"QA","dependsOn":"cael","blocked":true}'
  python3 update_status.py --queue-clear

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
                raw_time = parts[2].strip()
                # ISO 8601 변환: "2026-02-27 19:07:33 +0900" → "2026-02-27T19:07:33+09:00"
                try:
                    dt = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S %z")
                    iso_time = dt.isoformat(timespec="seconds")
                except ValueError:
                    iso_time = raw_time
                commits.append({
                    "hash": parts[0][:7],
                    "message": parts[1],
                    "time": iso_time
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
    return {"agents": [], "recentLogs": [], "deployUrl": "https://fourpillars-eosin.vercel.app", "nextTask": None, "queue": []}


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

    # ── flag parsing ──────────────────────────────────────────
    next_task_flag = None
    queue_add_flag = None
    queue_clear_flag = False
    positional = []

    i = 0
    while i < len(args):
        if args[i] == '--next-task' and i + 1 < len(args):
            next_task_flag = args[i + 1]
            i += 2
        elif args[i] == '--queue-add' and i + 1 < len(args):
            queue_add_flag = args[i + 1]
            i += 2
        elif args[i] == '--queue-clear':
            queue_clear_flag = True
            i += 1
        else:
            positional.append(args[i])
            i += 1

    agent_id = positional[0] if len(positional) > 0 else None
    new_status = positional[1] if len(positional) > 1 else None
    new_task = positional[2] if len(positional) > 2 else None

    valid_statuses = {"running", "done", "idle"}
    if new_status and new_status not in valid_statuses:
        print(f"[error] 유효하지 않은 상태: '{new_status}'. 사용 가능: {valid_statuses}")
        sys.exit(1)

    data = load_status()

    # ── nextTask ──────────────────────────────────────────────
    if next_task_flag is not None:
        if next_task_flag.strip().lower() == 'null':
            data['nextTask'] = None
            print("[ok] nextTask → null (완료 처리)")
        else:
            try:
                task_obj = json.loads(next_task_flag)
                data['nextTask'] = task_obj
                print(f"[ok] nextTask 설정: {task_obj.get('agentName')} — {task_obj.get('task')}")
            except json.JSONDecodeError as e:
                print(f"[error] --next-task JSON 파싱 실패: {e}")
                sys.exit(1)

    # ── queue-clear ───────────────────────────────────────────
    if queue_clear_flag:
        data['queue'] = []
        print("[ok] queue 초기화")

    # ── queue-add ─────────────────────────────────────────────
    if queue_add_flag is not None:
        try:
            item = json.loads(queue_add_flag)
            if 'queue' not in data:
                data['queue'] = []
            data['queue'].append(item)
            print(f"[ok] queue 추가: {item.get('agentName')} — {item.get('task')}")
        except json.JSONDecodeError as e:
            print(f"[error] --queue-add JSON 파싱 실패: {e}")
            sys.exit(1)

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
