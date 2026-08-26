# SOAR 파이프라인 — 타겟·공격 환경 (역할 A)

ELK–ipset 연동 SOAR 파이프라인 프로젝트의 **A 담당(인프라·타겟·공격)** 구축 파일 모음.
`kali · was · db` 3대 VM의 네트워크 설정, 3-Tier DVWA(웹앱 + 외부 DB), 공격 스크립트를 담는다.

> 이 저장소는 **기록 겸 재현용**이다. 팀원이 clone 해서 같은 환경을 세울 수 있도록 구성했다.
> 실환경 값(비밀번호 등)은 `.env`로 분리했고 `.gitignore`로 커밋에서 제외한다.

---

## 1. 환경 개요

- 가상화: **VMware Workstation** (VirtualBox도 가능, 메뉴만 다름)
- 게스트 OS: Ubuntu Server 22.04 (was·db) / Kali Linux (kali)
- 컨테이너: Docker + docker compose v2
- WAS 구성: **Apache + mod_php** (`php:8.0-apache`). PHP-FPM 아님 — 실습 규모에선 차이 없어 mod_php로 통일.

### VM별 역할

| VM | 역할 | 컨테이너 | 소유 |
| --- | --- | --- | --- |
| kali | 공격기 | (없음, 도구 직접 실행) | A |
| was | WAS Tier — DVWA 앱 | dvwa-app (php:8.0-apache) | A |
| db | DB Tier — MySQL | dvwa-db (mysql:8.0) | A |

---

## 2. 네트워크 세그먼트 · IP 할당

VMware에서 **LAN Segment**(VirtualBox의 "내부 네트워크")로 구간을 나눈다.

| 세그먼트 | 대역 | 연결 | 용도 |
| --- | --- | --- | --- |
| LAN0 | 192.168.10.0/24 | kali ↔ web | 외부·DMZ (유일한 외부 진입점) |
| LAN1 | 192.168.20.0/24 | web ↔ was | 리버스 프록시 구간 |
| LAN2 | 192.168.30.0/24 | was ↔ db | DB 질의 구간 |
| LAN3 | 192.168.40.0/24 | 전 VM ↔ soc | 관리망 |

### IP 할당표

| VM | LAN0 | LAN1 | LAN2 | LAN3 |
| --- | --- | --- | --- | --- |
| kali | .10.100 | — | — | — |
| web | .10.10 | .20.10 | — | .40.10 |
| **was** | — | **.20.20** | **.30.20** | **.40.20** |
| **db** | — | — | **.30.30** | **.40.30** |
| soc | — | — | — | .40.40 |

> web·soc는 B·D·C 담당. 이 저장소는 kali·was·db만 다룬다.
> **db에는 외부망(LAN0) NIC를 붙이지 않는다.**

### VMware 어댑터 매핑

| VM | 어댑터 구성 |
| --- | --- |
| was | Adapter1=lan1 / Adapter2=lan2 / Adapter3=lan3 / Adapter4=NAT(인터넷, 임시) |
| db | Adapter1=lan2 / Adapter2=lan3 / Adapter3=NAT(인터넷, 임시) |
| kali | Adapter1=lan0 / Adapter2=NAT(인터넷, 선택) |

> 각 어댑터는 **Advanced → Generate**로 MAC을 새로 생성한다. (복제 VM은 MAC이 겹치므로 필수)

---

## 3. 구축 순서

### 3-1. 네트워크 (was·db)

1. VMware에서 위 표대로 어댑터·LAN Segment·MAC 설정
2. VM 부팅 후 `ip a`로 실제 인터페이스 이름 확인 (예: ens32/ens35/ens36)
3. `network/` 아래 netplan 파일을 참고해 `/etc/netplan/01-network-manager-all.yaml` 작성
   - 인터페이스 이름은 실제 `ip a` 결과에 맞게 수정
   - **서버 VM은 `renderer: networkd` 사용** (NetworkManager는 인터페이스를 자동으로 안 켜는 경우가 있음)
4. 권한·적용:
   ```bash
   sudo chmod 600 /etc/netplan/01-network-manager-all.yaml
   sudo systemctl enable --now systemd-networkd
   sudo netplan apply
   ip a          # IP 붙었는지 확인
   ```
5. 연결 확인: was에서 `ping -c2 192.168.30.30` (was↔db LAN2)

### 3-2. 네트워크 (kali)

Kali는 netplan 대신 nmcli 사용:
```bash
sudo nmcli con mod "Wired connection 1" ipv4.addresses 192.168.10.100/24
sudo nmcli con mod "Wired connection 1" ipv4.method manual
sudo nmcli con down "Wired connection 1" && sudo nmcli con up "Wired connection 1"
```

### 3-3. chrony (was·db, 전 VM)

```bash
sudo apt update && sudo apt install -y chrony
```
soc VM이 생기면 `/etc/chrony/chrony.conf`의 pool 줄을 주석 처리하고 `server 192.168.40.40 iburst` 추가.
현재는 인터넷 시간 서버 기준으로 동작.
```bash
chronyc sources     # ^* 표시 확인 (측정 시작 전 필수)
```

### 3-4. Docker (was·db)

```bash
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
```

### 3-5. DB 컨테이너 (db VM)

```bash
cd db/
cp ../.env.example .env      # 값 확인/수정
docker compose up -d
docker logs dvwa-db          # "ready for connections" 확인
```

### 3-6. DVWA 컨테이너 (was VM)

```bash
# DVWA 소스 받기
git clone https://github.com/digininja/DVWA.git ~/DVWA
cp config.inc.php.patch ~/DVWA/config/config.inc.php   # 또는 아래 값만 수동 반영
cp docker-compose.yml ~/DVWA/
cp .env ~/DVWA/            # db와 동일한 계정 값

cd ~/DVWA
docker compose up -d
docker exec dvwa-app php -m | grep pdo   # pdo_mysql 확인
```

브라우저에서 `http://192.168.20.20:8080/setup.php` → **Create / Reset Database**.
`role column` 에러는 무시 가능(MySQL 8 문법 비호환, 부가기능이라 실습 무관).

로그인: `admin` / `password` → **DVWA Security를 Low로** 설정.

### 3-7. 계층별 인바운드 제한 (검증항목 4)

web VM IP가 확정된 뒤 적용 권장. `network/inbound-rules.sh` 참고.

---

## 4. 확정된 실제 값

| 항목 | 값 |
| --- | --- |
| db MySQL | 192.168.30.30:3306 (LAN2 IP에만 바인드) |
| DVWA 앱 | 192.168.20.20:8080 |
| DB 계정 | dvwa / dvwapass |
| DB 이름 | dvwa |
| MySQL root | rootpass |
| DVWA 로그인 | admin / password |
| kali 공격망 IP | 192.168.10.100 (eth0) |

---

## 5. 트러블슈팅 (구축 중 실제 발생)

### 네트워크

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| VM 3대 MAC 동일 | 복제(clone)로 생성 | 각 어댑터 Advanced→Generate로 MAC 재생성 |
| netplan apply 후에도 인터페이스 DOWN | renderer가 NetworkManager라 서버 인터페이스를 자동으로 안 켬 | `renderer: networkd`로 변경 + `systemctl enable --now systemd-networkd` |
| `systemd-networkd is not running` 경고 | networkd 서비스 꺼짐 | `sudo systemctl enable --now systemd-networkd` |
| netplan 파일 2개 충돌 | 00-installer-config.yaml + 01-...이 공존 | 안 쓰는 파일을 `.bak`으로 이름 변경 |
| `Permissions too open` 경고 | netplan 파일 권한 과다 | `sudo chmod 600 /etc/netplan/*.yaml` |
| `Cannot call Open vSwitch` 경고 | OVS 미사용 기능 경고 | 무시 |

### Docker / DVWA

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| `curl` 없음 | Ubuntu 최소 설치 | 스크립트 대신 `apt install docker.io docker-compose-v2` |
| apt lock (`held by unattended-upgr`) | 부팅 후 자동 보안 업데이트가 apt 점유 | `sudo kill -9 <pid>` → `sudo dpkg --configure -a` → `sudo systemctl disable unattended-upgrades`. **`rm`으로 lock 강제 삭제 금지** |
| `pdo_mysql: Missing` (setup.php) | compose에서 mysqli만 설치 | `command`에 `pdo pdo_mysql` 추가 후 재기동 |
| `Writable folder ... No` | 컨테이너 내 디렉터리 쓰기 권한 없음 | compose `command`에 `chmod -R 777 .../uploads .../config` |
| Create DB 시 `role column` SQL 에러 | DVWA가 MariaDB 문법 사용, MySQL 8 비호환 | 무시 가능. users 테이블·데이터는 정상 생성 |
| DVWA가 db VM 대신 내장 DB 사용 | config 미수정 | config.inc.php의 db_server를 192.168.30.30으로 |
| caching_sha2_password 인증 실패 | MySQL 8 기본 인증 | `mysql_native_password`로 지정 (compose command) |

### kali

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| eth1이 엉뚱한 대역(192.168.100.x) | 교수 이미지의 기존 어댑터 설정 잔존 | kali는 eth0(lan0)만 있으면 됨. 인터넷 불필요하면 `sudo ip link set eth1 down` |
| dhclient not found | Kali 최신은 dhclient 미포함 | `sudo systemctl restart NetworkManager` 또는 무시 |

---

## 6. 다음 작업 (미완)

- [ ] 계층별 인바운드 제한 (web IP 확정 후, `network/inbound-rules.sh`)
- [ ] web·soc VM 생성 후 전 구간 관통 (B·C·D와 통합)
- [ ] 공격 스크립트 실전 실행 (web 진입점 생긴 뒤)
