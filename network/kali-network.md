# kali 네트워크 설정

Kali는 netplan을 쓰지 않고 NetworkManager(nmcli)를 쓴다.
kali는 LAN0(공격망) 하나만 있으면 된다. eth0 = 192.168.10.100.

## 어댑터 (VMware)
- Adapter 1 = LAN segment `lan0` (MAC Generate)
- Adapter 2 = NAT (인터넷, 선택 — 공격 도구 설치용. 불필요하면 꺼도 됨)

## IP 설정
인터페이스 이름 확인:
```bash
ip a          # 보통 eth0
```

고정 IP 부여:
```bash
sudo nmcli con mod "Wired connection 1" ipv4.addresses 192.168.10.100/24
sudo nmcli con mod "Wired connection 1" ipv4.method manual
sudo nmcli con down "Wired connection 1" && sudo nmcli con up "Wired connection 1"
ip a          # 192.168.10.100 확인
```

## 참고
- 교수 배포 이미지는 eth1이 다른 대역(192.168.100.x)을 잡을 수 있다.
  kali는 eth0만 필요하므로, 불필요하면: `sudo ip link set eth1 down`
- 공격 스크립트에 필요한 requests는 Kali에 기본 설치돼 있다:
  `python3 -c "import requests; print('ok')"`
- docker0 인터페이스가 보여도 kali는 Docker를 쓰지 않으므로 무시.
