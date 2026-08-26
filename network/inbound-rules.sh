#!/usr/bin/env bash
# 계층별 인바운드 제한 (3-Tier 강제 · 검증항목 4)
# was·db에서 각각 해당 부분을 실행한다. web VM IP가 확정된 뒤 적용 권장.
#
# 목적: kali가 web을 우회해 was/db로 직접 들어오는 경로를 차단.
#       하위 계층이 열려 있으면 web의 ipset을 우회할 수 있어 3-Tier가 무너진다.

set -euo pipefail

WEB_LAN1_IP="192.168.20.10"   # web VM의 LAN1 IP
WAS_LAN2_IP="192.168.30.20"   # was VM의 LAN2 IP

case "${1:-}" in
  was)
    # was: 8080은 web VM에서 오는 것만 허용
    sudo iptables -A INPUT -p tcp --dport 8080 -s "${WEB_LAN1_IP}" -j ACCEPT
    sudo iptables -A INPUT -p tcp --dport 8080 -j DROP
    echo "[was] 8080 인바운드를 ${WEB_LAN1_IP} 만 허용하도록 설정"
    ;;
  db)
    # db: 3306은 was VM에서 오는 것만 허용
    sudo iptables -A INPUT -p tcp --dport 3306 -s "${WAS_LAN2_IP}" -j ACCEPT
    sudo iptables -A INPUT -p tcp --dport 3306 -j DROP
    echo "[db] 3306 인바운드를 ${WAS_LAN2_IP} 만 허용하도록 설정"
    ;;
  *)
    echo "사용법: $0 [was|db]"
    echo "  was VM에서는:  $0 was"
    echo "  db  VM에서는:  $0 db"
    exit 1
    ;;
esac

echo "재부팅 후에도 유지하려면: sudo apt install -y iptables-persistent && sudo netfilter-persistent save"
