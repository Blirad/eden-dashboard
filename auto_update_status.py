#!/usr/bin/env python3
"""
auto_update_status.py — 에이전트 상태 자동 감지 및 대시보드 갱신

openclaw sessions --all-agents --json 으로 활성 세션을 감지하여
status.json을 자동 업데이트하고 git push한다.

크론 등록 예시:
  openclaw cron add --schedule "*/2 * * * *" \
    --command "python3 ~/Projects/dashboard/auto_update_status.py" \
    --name "dashboard-auto-update"
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

# 활성으로 간주할 세션 나이 (분)
ACTIVE_WINDOW_MINUTES = 5

# 에이전트 ID → 대시보드 agent id 매핑
AGENT_MAP = {
    "main": "bilard",  # main 세션 = 빌라드 직접 작업
    "cael": "cael",
    "quinn": "quinn",
    "dorian": "dorian",
    "mira": "mira",
    "lyra": "lyra",
    "knox": "knox",
    "rex": "rex",
}

# subagent 세션 키 패턴 → 소속 에이전트 추출
# "agent:knox:subagent:..." → "knox"


def get_active_sessions():
    """openclaw sessions로 활성 세션 목록 반환"""
    try:
        result = subprocess.run(
            ["openclaw", "sessions", "--all-agents",
             "--active", str(ACTIVE_WINDOW_MINUTES), "--json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            print(f"[warn] openclaw sessions 실패: {result.stderr[:200]}", file=sys.stderr)
            return []
        data = json.loads(result.stdout)
        return data.get("sessions", [])
    except Exception as e:
        print(f"[warn] 세션 읽기 오류: {e}", file=sys.stderr)
        return []


def extract_agent_id_from_session(session):
    """세션에서 에이전트 ID 추출"""
    # agentId 필드 우선
    agent_id = session.get("agentId", "")
    if agent_id:
        return agent_id
    # key에서 추출: "agent:knox:subagent:..." → "knox"
    key = session.get("key", "")
    parts = key.split(":")
    if len(parts) >= 2:
        return parts[1]
    return None


def get_active_agent_ids(sessions):
    """활성 세션에서 에이전트 ID 집합 반환"""
    active = set()
    for s in sessions:
        agent_id = extract_agent_id_from_session(s)
        if agent_id:
            active.add(agent_id)
    return active


def get_git_log(n=5):
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
    return {"agents": [], "recentLogs": [], "deployUrl": "", "nextTask": None, "queue": []}


def save_status(data):
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def now_kst():
    return datetime.now(KST).isoformat(timespec="seconds")


def deploy_vercel():
    """Vercel CLI로 직접 배포 (git remote 불필요)"""
    vercel_bin = Path.home() / ".npm-global/bin/vercel"
    if not vercel_bin.exists():
        vercel_bin = Path("/usr/local/bin/vercel")
    try:
        result = subprocess.run(
            [str(vercel_bin), "--prod", "--yes"],
            capture_output=True, text=True, timeout=60,
            cwd=str(SCRIPT_DIR)
        )
        if result.returncode == 0:
            # 배포 URL 추출
            lines = (result.stdout + result.stderr).splitlines()
            url = next((l.strip() for l in lines if "vercel.app" in l), "")
            print(f"[ok] Vercel 배포 완료 {url}")
            return True
        else:
            print(f"[error] Vercel 배포 실패:\n{result.stderr[:300]}", file=sys.stderr)
            return False
    except subprocess.TimeoutExpired:
        print("[error] Vercel 배포 타임아웃", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[error] Vercel 배포 오류: {e}", file=sys.stderr)
        return False


def main():
    sessions = get_active_sessions()
    active_ids = get_active_agent_ids(sessions)
    print(f"[info] 활성 세션 에이전트: {active_ids}")

    data = load_status()

    # git log 갱신
    commits = get_git_log(10)
    if commits:
        data["recentLogs"] = []
        for c in commits[:5]:
            data["recentLogs"].append({
                "agentId": "bilard",
                "agentName": "빌라드",
                "agentEmoji": "👑",
                "message": c["message"],
                "time": c["time"]
            })
        latest = commits[0]
        for agent in data["agents"]:
            if agent["id"] == "bilard":
                agent["lastCommit"] = latest["message"]
                agent["lastCommitTime"] = latest["time"]
                break

    # 에이전트 상태 자동 갱신
    changed_agents = []
    for agent in data["agents"]:
        agent_id = agent["id"]
        # 대시보드 ID → openclaw 에이전트 ID 역매핑
        oc_id = None
        for oc, dash in AGENT_MAP.items():
            if dash == agent_id:
                oc_id = oc
                break

        if oc_id is None:
            continue

        is_active = oc_id in active_ids

        # 현재 상태가 이미 적절하면 건드리지 않음
        current_status = agent.get("status", "idle")

        if is_active and current_status == "idle":
            # idle → running 자동 전환
            agent["status"] = "running"
            if not agent.get("currentTask"):
                agent["currentTask"] = "작업 중..."
            changed_agents.append(f"{agent['emoji']} {agent['name']} → running")
        elif not is_active and current_status == "running":
            # running → done 전환 (세션이 사라지면 완료 처리)
            agent["status"] = "done"
            changed_agents.append(f"{agent['emoji']} {agent['name']} → done")

    if changed_agents:
        print(f"[ok] 상태 변경: {', '.join(changed_agents)}")
    else:
        print("[info] 상태 변경 없음")

    data["updatedAt"] = now_kst()
    save_status(data)
    print(f"[ok] status.json 저장: {STATUS_FILE}")

    # Vercel 배포
    deploy_vercel()


if __name__ == "__main__":
    main()
