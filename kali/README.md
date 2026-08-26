# kali — 공격 스크립트

`attacks.py` : DVWA 대상 공격 시나리오 드라이버 (규약1의 5종 공격 + 차단 감지 probe).

## 준비
```bash
# requests는 Kali에 기본 설치됨. 없으면:
pip3 install requests

export DVWA_URL=http://192.168.10.10        # 외부 진입점(web VM). web 생긴 뒤 사용
```

## 실행
```bash
# 개별 공격
python3 attacks.py sqli
python3 attacks.py command_injection
python3 attacks.py webshell_upload
python3 attacks.py brute_force --count 30
python3 attacks.py dir_scan --count 150

# 5종 순차
python3 attacks.py all

# 차단 발효 시점 측정 (TTB 외부 검증)
python3 attacks.py probe --measure
```

## 공격 → 차단 유형 매핑

| attack_type | 차단 조건 | 드라이버 기본 강도 |
| --- | --- | --- |
| webshell_upload | 1건 즉시 | count=1 |
| command_injection | 1건 즉시 | count=1 |
| sqli | 5분 내 5건 | count=5 |
| brute_force | 1분 내 20건 | count=25 |
| dir_scan | 5분 내 404 100건 | count=120 |

> web VM(진입점)과 soc VM(ELK)이 있어야 전 구간이 돈다. 현재는 스크립트만 준비된 상태.
> 공격 유형 코드 5종은 규약1의 attack.type / 규약2의 attack_type과 글자까지 동일해야 한다.
