# 2. Keys and data

krx-lean doesn't ship data. You download it from the official sources with your own free keys
(approval can take a day, so start here early).

## KRX Open API key (required: prices and indices)

1. Sign up at <https://openapi.krx.co.kr/> (**회원가입**) and log in.
2. **마이페이지 → API 인증키 신청**: request a key (40 letters and digits).
3. Under **서비스 이용**, open each service below, click **API 이용신청**, and choose **12M**:

   | Category | Service | Gives |
   |---|---|---|
   | 주식 | 유가증권 일별매매정보 | KOSPI daily prices |
   | 증권상품 | ETF 일별매매정보 | ETF daily prices |
   | 지수 | KOSPI 시리즈 일별시세정보 | KOSPI, KOSPI 200 and the rest of the family |
   | 주식 | 유가증권 종목기본정보 | ISIN, listing date, share class (optional) |

4. Approval usually takes up to a day (**마이페이지 → 이용현황**).
   `401 Unauthorized Key` = the key is wrong; `401 Unauthorized API Call` = that service isn't
   approved yet.

## data.go.kr key (recommended: dividends)

Without it prices are adjusted for splits and rights issues but **not for dividends**.

1. Sign up at <https://www.data.go.kr/> and log in.
2. Apply (**활용신청**, usually approved at once) for:
   - 금융위원회_주식배당정보 — <https://www.data.go.kr/data/15043284/openapi.do>
   - 금융위원회_주식권리일정정보 (optional, corporate-action dates) — <https://www.data.go.kr/data/15059609/openapi.do>
3. **마이페이지 → 데이터활용 → Open API → 활용신청 현황**: copy the **일반 인증키 (Decoding)**.
   A new key can take about an hour to start working.

## Store the keys

Keys are read from environment variables only. Keep them in a file only you can read, outside
the repository and the workspace:

```bash
mkdir -p ~/.config && touch ~/.config/krx-lean.env && chmod 600 ~/.config/krx-lean.env
nano ~/.config/krx-lean.env
```

```bash
KRX_API_KEY=your-krx-key
DATA_GO_KR_KEY=your-data-go-kr-decoding-key
```

Load them into a shell before downloading:

```bash
set -a; . ~/.config/krx-lean.env; set +a
```

Never put keys in code, notebooks or commits. If a key is exposed, reissue it on the site.

## First download and build

```bash
krx-lean --root ~/krx-data all
```

This downloads KOSPI and ETF daily prices and the KOSPI index family from 2010-01-04, the
dividend table (if `DATA_GO_KR_KEY` is set), and builds everything LEAN needs under
`~/krx-data/lean/`. The first run makes about 13,000 calls and takes **1.5–2 hours**; later runs
fetch only new days. It's resumable: if it stops (network, quota), run it again.

Optional extras:

```bash
krx-lean --root ~/krx-data krx-info     # security master: ISIN, share class, par value
krx-lean --root ~/krx-data rights       # corporate-action dates (15–25 min)
krx-lean --root ~/krx-data build        # rebuild after the extras
```

## Check the data

```bash
column -s, -t < ~/krx-data/securities.csv | head        # securities with their first/last dates
grep -E '^(20180503|20180504)' ~/krx-data/ohlcv/005930.csv   # Samsung 50:1 split: 2,650,000 → 51,900
```

The data folder (`~/krx-data`):

| Folder / file | Content |
|---|---|
| `raw/` | the downloads, exactly as received (everything else is rebuilt from it) |
| `lean/` | LEAN's format: `equity/krx/{daily, factor_files, map_files, universe}`, `index/krx/daily` |
| `ohlcv/`, `index/` | plain CSVs per security / index, for your own research |
| `securities.csv` | code → market (KOSPI / ETF), listing span |
| `dividends.csv`, `factor_events.csv` | dividends used, and every price adjustment (audit trail) |

Next: [3. Workspace and first backtest](3-first-backtest.md).
