# krx-lean

[English](README.md) · **한국어**

한국 주식시장(KRX) 데이터와 시장 모델을 오픈소스 백테스트 엔진
[QuantConnect LEAN](https://github.com/QuantConnect/Lean)에서 쓸 수 있게 해 주는 도구입니다. LEAN을 내 컴퓨터에서
소스로 빌드해, KOSPI·KOSDAQ 주식과 ETF 전략을 Python이나 C#으로 백테스트합니다. KRX 수수료와 증권거래세, 호가가격단위,
선택 가능한 슬리피지, KOSPI 200 벤치마크, 상장폐지 종목을 포함한 일별 유니버스, 액면분할·유무상증자·배당을 반영한
수정주가를 지원하며, Jupyter 노트북(LEAN QuantBook)으로 데이터를 살펴볼 수 있습니다.

모든 것이 내 컴퓨터에서 실행됩니다. Docker, QuantConnect 계정, 클라우드 서비스가 필요 없습니다. 데이터는 본인의
무료 API 인증키로 직접 내려받습니다.

**처음이신가요?** [초보자 안내(한국어)](https://pinjoy99.github.io/krx-lean/ko/)를 따라 하면 새 컴퓨터에서 첫
백테스트와 노트북까지 한 시간 안에 해 볼 수 있습니다. 인증키가 없어도 가상(합성) 데모 데이터로 먼저 써 볼 수 있습니다.

## 범위

- **대상:** KOSPI 주식, ETF, 그리고 KOSDAQ 주식(신규, KRX에서 코스닥 서비스 이용 승인 필요)의 일별 데이터(2010년 이후).
  KONEX, NXT, 분 단위 데이터, 실거래는 다루지 않습니다.
- **플랫폼:** Linux(Ubuntu 24.04 / 22.04에서 테스트)와 WSL2를 통한 Windows. Apple Silicon macOS는 자동 종단 간 검사를 통과했습니다(실험적: 사람이 직접 따라 해 보지는
  않았습니다. [설치 안내](docs/user/1-install.md#macos) 참조).

## 빠르게 보기

```bash
klean init ~/krx-demo --lean ~/Lean --python-venv ~/.klean/py311
cd ~/krx-demo && klean install data --demo        # 가상 데모 데이터 (인증키 불필요)
klean create project Top20 --template top-market-cap
klean backtest Top20                               # 슬리피지는 기본 꺼짐: --parameter slippage_ticks 1 로 켭니다
klean report Top20
klean gui
klean research Top20
```

실제 데이터: [KRX Open API](https://openapi.krx.co.kr/)(시세)와 [공공데이터포털](https://www.data.go.kr/)(배당)의
무료 인증키를 받은 뒤 `krx-lean --root ~/krx-data all`로 내려받고, 이후에는 워크스페이스에서 `klean update data`로 갱신합니다. `klean update all`은 krx-lean, (필요하면) LEAN, 데이터를 한 번에 갱신합니다.

## 문서

| | |
|---|---|
| [초보자 안내 (한국어)](https://pinjoy99.github.io/krx-lean/ko/) | 설치부터 첫 백테스트, 결과 읽기, 실제 데이터, 나만의 전략 |
| [사용자 안내서 (영문)](docs/user/) | 설치, 데이터, 전략, 도구, 매일 업데이트, 문제 해결 |
| [개발자 안내서 (영문)](docs/dev/) | 데이터 규칙, KRX 모델, LEAN 빌드, klean 내부, 테스트 |
| [기여 방법](CONTRIBUTING.md) · [보안 정책](SECURITY.md) · [변경 내역](CHANGELOG.md) | 영문 |

자세한 안내서는 아직 영문만 있습니다. 질문과 버그 제보는 [이슈](https://github.com/pinjoy99/krx-lean/issues)로
한국어로 남겨 주셔도 됩니다.

## 라이선스와 데이터

krx-lean은 [Apache-2.0](LICENSE) 라이선스입니다. QuantConnect 및 한국거래소와 관련이 없습니다([NOTICE](NOTICE)).
시장 데이터는 포함되어 있지 않습니다. 내려받은 데이터는 각 제공처(KRX Open API, 공공데이터포털 공공누리)의
이용약관을 따르며 재배포하면 안 됩니다. 이 프로젝트의 어떤 내용도 투자 조언이 아닙니다.
