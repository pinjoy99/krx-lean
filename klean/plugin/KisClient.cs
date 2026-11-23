/*
 * Korea Investment & Securities (KIS) Open API: the calls klean's KIS-PAPER brokerage needs, for
 * 모의투자 (paper) accounts only: klean never connects to KIS's real-trading server. Endpoints
 * and tr_ids as in KIS's official samples (github.com/koreainvestment/open-trading-api).
 * Credentials come from the environment, never from files klean writes: KIS_PAPER_APP_KEY,
 * KIS_PAPER_APP_SECRET, KIS_PAPER_ACCOUNT ("12345678-01"), KIS_PAPER_BASE_URL (tests only).
 * Tokens (one a day; KIS issues at most one a minute) are cached in ~/.klean/kis-token-*.json.
 */
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using QuantConnect.Logging;

namespace QuantConnect.Krx
{
    public record KisHolding(string Code, decimal Quantity, decimal AveragePrice, decimal Price);
    public record KisBalance(decimal Cash, decimal TotalValue, List<KisHolding> Holdings);
    public record KisOrderResult(string OrderNo, string BranchNo, string Time);
    public record KisExecution(string Date, string OrderNo, string Code, bool Buy, decimal OrderQuantity,
        decimal FilledQuantity, decimal AveragePrice, decimal Remaining, bool Canceled, decimal Rejected);

    public class KisException : Exception
    {
        public string Code { get; }
        public KisException(string code, string message) : base($"KIS {code}: {message}") { Code = code; }
    }

    public class KisClient : IDisposable
    {
        public const string PaperUrl = "https://openapivts.koreainvestment.com:29443";   // 모의투자

        private readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(20) };
        private readonly string _appKey, _appSecret, _cano, _product, _baseUrl;
        private readonly TimeSpan _gap;
        private DateTime _lastCall = DateTime.MinValue;
        private string _token;

        public static bool Configured => !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("KIS_PAPER_APP_KEY"));

        public KisClient()
        {
            string Env(string name) => Environment.GetEnvironmentVariable(name)
                ?? throw new InvalidOperationException($"{name} is not set (klean reads it from ~/.config/krx-lean.env)");
            _appKey = Env("KIS_PAPER_APP_KEY");
            _appSecret = Env("KIS_PAPER_APP_SECRET");
            var account = Env("KIS_PAPER_ACCOUNT").Replace(" ", "");
            var parts = account.Split('-');
            _cano = parts[0];
            _product = parts.Length > 1 ? parts[1] : account.Length == 10 ? account.Substring(8) : "01";
            if (_cano.Length == 10) _cano = _cano.Substring(0, 8);
            _baseUrl = (Environment.GetEnvironmentVariable("KIS_PAPER_BASE_URL") ?? PaperUrl).TrimEnd('/');
            _gap = TimeSpan.FromMilliseconds(550);                  // KIS limits calls per second, lower for 모의투자
        }

        // ------------------------------------------------------------------ plumbing


        private string TokenPath()
        {
            var hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(_baseUrl + _appKey))).Substring(0, 12).ToLowerInvariant();
            var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".klean");
            Directory.CreateDirectory(dir);
            return Path.Combine(dir, $"kis-token-paper-{hash}.json");
        }

        private string Token()
        {
            if (_token != null) return _token;
            var path = TokenPath();
            if (File.Exists(path))
            {
                using var cached = JsonDocument.Parse(File.ReadAllText(path));
                var expires = DateTime.Parse(cached.RootElement.GetProperty("expires_utc").GetString(), CultureInfo.InvariantCulture,
                    DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal);
                if (expires > DateTime.UtcNow.AddMinutes(30)) return _token = cached.RootElement.GetProperty("token").GetString();
            }
            var body = JsonSerializer.Serialize(new { grant_type = "client_credentials", appkey = _appKey, appsecret = _appSecret });
            using var response = _http.PostAsync(_baseUrl + "/oauth2/tokenP", new StringContent(body, Encoding.UTF8, "application/json")).Result;
            var text = response.Content.ReadAsStringAsync().Result;
            using var doc = JsonDocument.Parse(text);
            if (!doc.RootElement.TryGetProperty("access_token", out var token))
            {
                var code = doc.RootElement.TryGetProperty("error_code", out var c) ? c.GetString() : ((int)response.StatusCode).ToString(CultureInfo.InvariantCulture);
                var msg = doc.RootElement.TryGetProperty("error_description", out var m) ? m.GetString() : text;
                throw new KisException(code, "token: " + msg);
            }
            _token = token.GetString();
            var hours = doc.RootElement.TryGetProperty("expires_in", out var e) && e.TryGetInt32(out var s) ? s / 3600.0 : 24;
            File.WriteAllText(path, JsonSerializer.Serialize(new { token = _token, expires_utc = DateTime.UtcNow.AddHours(hours).ToString("o") }));
            if (!OperatingSystem.IsWindows()) File.SetUnixFileMode(path, UnixFileMode.UserRead | UnixFileMode.UserWrite);
            return _token;
        }

        private JsonElement Call(HttpMethod method, string path, string trId, Dictionary<string, string> data, string trCont = "")
        {
            for (var attempt = 0; ; attempt++)
            {
                var wait = _gap - (DateTime.UtcNow - _lastCall);
                if (wait > TimeSpan.Zero) Thread.Sleep(wait);
                _lastCall = DateTime.UtcNow;
                var url = _baseUrl + path;
                if (method == HttpMethod.Get)
                {
                    url += "?" + string.Join("&", data.Select(kv => $"{kv.Key}={Uri.EscapeDataString(kv.Value)}"));
                }
                using var request = new HttpRequestMessage(method, url);
                request.Headers.TryAddWithoutValidation("authorization", "Bearer " + Token());
                request.Headers.TryAddWithoutValidation("appkey", _appKey);
                request.Headers.TryAddWithoutValidation("appsecret", _appSecret);
                request.Headers.TryAddWithoutValidation("tr_id", trId);
                request.Headers.TryAddWithoutValidation("tr_cont", trCont);
                request.Headers.TryAddWithoutValidation("custtype", "P");
                if (method == HttpMethod.Post)
                {
                    request.Content = new StringContent(JsonSerializer.Serialize(data), Encoding.UTF8, "application/json");
                }
                using var response = _http.SendAsync(request).Result;
                var text = response.Content.ReadAsStringAsync().Result;
                var root = JsonDocument.Parse(text).RootElement.Clone();
                var rt = root.TryGetProperty("rt_cd", out var r) ? r.GetString() : "";
                if (rt == "0") return root;
                var code = root.TryGetProperty("msg_cd", out var c) ? c.GetString() : "";
                var msg = root.TryGetProperty("msg1", out var m) ? m.GetString() : text;
                if (code == "EGW00201" && attempt < 5)            // too many calls per second: wait and retry
                {
                    Thread.Sleep(1000 * (attempt + 1));
                    continue;
                }
                if (code == "EGW00123" && attempt == 0)           // expired token: get a new one once
                {
                    _token = null;
                    File.Delete(TokenPath());
                    continue;
                }
                throw new KisException(code, msg.Trim());
            }
        }

        private static decimal D(JsonElement e, string name)
            => e.TryGetProperty(name, out var v) && decimal.TryParse(v.GetString(), NumberStyles.Any, CultureInfo.InvariantCulture, out var d) ? d : 0m;

        private static string S(JsonElement e, string name) => e.TryGetProperty(name, out var v) ? v.GetString() ?? "" : "";

        // ------------------------------------------------------------------ account

        public KisBalance Balance()
        {
            var holdings = new List<KisHolding>();
            JsonElement summary = default;
            string fk = "", nk = "", cont = "";
            for (var page = 0; page < 20; page++)
            {
                var root = Call(HttpMethod.Get, "/uapi/domestic-stock/v1/trading/inquire-balance", "VTTC8434R", new()
                {
                    ["CANO"] = _cano, ["ACNT_PRDT_CD"] = _product, ["AFHR_FLPR_YN"] = "N", ["OFL_YN"] = "",
                    ["INQR_DVSN"] = "02", ["UNPR_DVSN"] = "01", ["FUND_STTL_ICLD_YN"] = "N", ["FNCG_AMT_AUTO_RDPT_YN"] = "N",
                    ["PRCS_DVSN"] = "00", ["CTX_AREA_FK100"] = fk, ["CTX_AREA_NK100"] = nk,
                }, cont);
                foreach (var h in root.GetProperty("output1").EnumerateArray())
                {
                    var qty = D(h, "hldg_qty");
                    if (qty != 0) holdings.Add(new KisHolding(S(h, "pdno"), qty, D(h, "pchs_avg_pric"), D(h, "prpr")));
                }
                var o2 = root.GetProperty("output2");
                summary = o2.ValueKind == JsonValueKind.Array ? o2[0] : o2;
                fk = S(root, "ctx_area_fk100").Trim();
                nk = S(root, "ctx_area_nk100").Trim();
                if (string.IsNullOrEmpty(nk) || root.GetProperty("output1").GetArrayLength() == 0) break;
                cont = "N";
            }
            // cash available to buy: the deposit after T+2 settlement (D+2 예수금)
            var cash = D(summary, "prvs_rcdl_excc_amt");
            if (cash == 0) cash = D(summary, "dnca_tot_amt");
            return new KisBalance(cash, D(summary, "tot_evlu_amt"), holdings);
        }

        // ------------------------------------------------------------------ orders

        /// <summary>A cash order: market (price 0) or limit. Returns KIS's order number.</summary>
        public KisOrderResult Order(string code, decimal quantity, decimal? limitPrice)
        {
            var buy = quantity > 0;
            var root = Call(HttpMethod.Post, "/uapi/domestic-stock/v1/trading/order-cash", buy ? "VTTC0012U" : "VTTC0011U", new()
            {
                ["CANO"] = _cano, ["ACNT_PRDT_CD"] = _product, ["PDNO"] = code,
                ["ORD_DVSN"] = limitPrice.HasValue ? "00" : "01",
                ["ORD_QTY"] = Math.Abs(quantity).ToString("0", CultureInfo.InvariantCulture),
                ["ORD_UNPR"] = (limitPrice ?? 0m).ToString("0", CultureInfo.InvariantCulture),
                ["EXCG_ID_DVSN_CD"] = "KRX", ["SLL_TYPE"] = buy ? "" : "01", ["CNDT_PRIC"] = "",
            });
            var o = root.GetProperty("output");
            return new KisOrderResult(S(o, "ODNO"), S(o, "KRX_FWDG_ORD_ORGNO"), S(o, "ORD_TMD"));
        }

        public void Cancel(string orderNo, string branchNo)
        {
            Call(HttpMethod.Post, "/uapi/domestic-stock/v1/trading/order-rvsecncl", "VTTC0013U", new()
            {
                ["CANO"] = _cano, ["ACNT_PRDT_CD"] = _product, ["KRX_FWDG_ORD_ORGNO"] = branchNo, ["ORGN_ODNO"] = orderNo,
                ["ORD_DVSN"] = "00", ["RVSE_CNCL_DVSN_CD"] = "02", ["ORD_QTY"] = "0", ["ORD_UNPR"] = "0",
                ["QTY_ALL_ORD_YN"] = "Y", ["EXCG_ID_DVSN_CD"] = "KRX",
            });
        }

        /// <summary>Orders and their fills between two dates (yyyyMMdd), within the last 3 months.</summary>
        public List<KisExecution> Executions(string from, string to)
        {
            var list = new List<KisExecution>();
            string fk = "", nk = "", cont = "";
            for (var page = 0; page < 50; page++)
            {
                var root = Call(HttpMethod.Get, "/uapi/domestic-stock/v1/trading/inquire-daily-ccld", "VTTC0081R", new()
                {
                    ["CANO"] = _cano, ["ACNT_PRDT_CD"] = _product, ["INQR_STRT_DT"] = from, ["INQR_END_DT"] = to,
                    ["SLL_BUY_DVSN_CD"] = "00", ["PDNO"] = "", ["CCLD_DVSN"] = "00", ["INQR_DVSN"] = "01", ["INQR_DVSN_3"] = "00",
                    ["ORD_GNO_BRNO"] = "", ["ODNO"] = "", ["INQR_DVSN_1"] = "", ["CTX_AREA_FK100"] = fk, ["CTX_AREA_NK100"] = nk,
                    ["EXCG_ID_DVSN_CD"] = "KRX",
                }, cont);
                var rows = root.GetProperty("output1");
                foreach (var e in rows.EnumerateArray())
                {
                    list.Add(new KisExecution(S(e, "ord_dt"), S(e, "odno"), S(e, "pdno"), S(e, "sll_buy_dvsn_cd") == "02",
                        D(e, "ord_qty"), D(e, "tot_ccld_qty"), D(e, "avg_prvs"), D(e, "rmn_qty"), S(e, "cncl_yn") == "Y", D(e, "rjct_qty")));
                }
                fk = S(root, "ctx_area_fk100").Trim();
                nk = S(root, "ctx_area_nk100").Trim();
                if (string.IsNullOrEmpty(nk) || rows.GetArrayLength() == 0) break;
                cont = "N";
            }
            return list;
        }

        // ------------------------------------------------------------------ prices

        /// <summary>A day's raw (unadjusted) prices of a stock, or null if it didn't trade that day.</summary>
        public DailyBar GetDailyBar(string code, DateTime day)
        {
            var key = day.ToString("yyyyMMdd", CultureInfo.InvariantCulture);
            var root = Call(HttpMethod.Get, "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100", new()
            {
                ["FID_COND_MRKT_DIV_CODE"] = "J", ["FID_INPUT_ISCD"] = code, ["FID_INPUT_DATE_1"] = key,
                ["FID_INPUT_DATE_2"] = key, ["FID_PERIOD_DIV_CODE"] = "D", ["FID_ORG_ADJ_PRC"] = "1",
            });
            if (!root.TryGetProperty("output2", out var rows) || rows.ValueKind != JsonValueKind.Array) return null;
            foreach (var r in rows.EnumerateArray())
            {
                if (S(r, "stck_bsop_date") != key || D(r, "stck_clpr") == 0) continue;
                return new DailyBar(day, D(r, "stck_oprc"), D(r, "stck_hgpr"), D(r, "stck_lwpr"), D(r, "stck_clpr"), D(r, "acml_vol"));
            }
            Log.Trace($"KisClient: no {key} bar for {code}");
            return null;
        }

        public void Dispose() => _http.Dispose();
    }
}
