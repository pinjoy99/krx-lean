/*
 * klean's KRX paper-trading account: cash, holdings, waiting orders, fills and daily equity,
 * kept in a JSON file between the daily runs (one LEAN process per trading day). Written by
 * KrxPaperBrokerage; created and read by klean (klean/live.py) and its GUI.
 */
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace QuantConnect.Krx
{
    public class LedgerHolding
    {
        [JsonPropertyName("quantity")] public decimal Quantity { get; set; }
        [JsonPropertyName("average_price")] public decimal AveragePrice { get; set; }
    }

    public class LedgerOrder
    {
        [JsonPropertyName("id")] public int Id { get; set; }
        [JsonPropertyName("symbol")] public string Symbol { get; set; }
        [JsonPropertyName("type")] public string Type { get; set; }          // Market, MarketOnOpen, MarketOnClose, Limit
        [JsonPropertyName("quantity")] public decimal Quantity { get; set; } // + buy, - sell
        [JsonPropertyName("limit_price")] public decimal? LimitPrice { get; set; }
        [JsonPropertyName("placed_session")] public string PlacedSession { get; set; }   // the data day it was placed on
        [JsonPropertyName("placed_utc")] public string PlacedUtc { get; set; }
        [JsonPropertyName("tag")] public string Tag { get; set; }
        [JsonPropertyName("kis_order_no")] public string KisOrderNo { get; set; }      // KIS deployments
        [JsonPropertyName("kis_branch_no")] public string KisBranchNo { get; set; }
        [JsonPropertyName("sent_date")] public string SentDate { get; set; }           // yyyyMMdd (KST) it went to KIS
    }

    public class LedgerFill
    {
        [JsonPropertyName("order_id")] public int OrderId { get; set; }
        [JsonPropertyName("session")] public string Session { get; set; }
        [JsonPropertyName("symbol")] public string Symbol { get; set; }
        [JsonPropertyName("quantity")] public decimal Quantity { get; set; }
        [JsonPropertyName("price")] public decimal Price { get; set; }
        [JsonPropertyName("commission")] public decimal Commission { get; set; }
        [JsonPropertyName("tax")] public decimal Tax { get; set; }
        [JsonPropertyName("type")] public string Type { get; set; }
        [JsonPropertyName("tag")] public string Tag { get; set; }
    }

    public class LedgerEvent       // orders that ended without a fill (rejected, canceled, not affordable)
    {
        [JsonPropertyName("order_id")] public int OrderId { get; set; }
        [JsonPropertyName("session")] public string Session { get; set; }
        [JsonPropertyName("symbol")] public string Symbol { get; set; }
        [JsonPropertyName("status")] public string Status { get; set; }
        [JsonPropertyName("message")] public string Message { get; set; }
    }

    public class LedgerEquity
    {
        [JsonPropertyName("session")] public string Session { get; set; }
        [JsonPropertyName("cash")] public decimal Cash { get; set; }
        [JsonPropertyName("holdings_value")] public decimal HoldingsValue { get; set; }
        [JsonPropertyName("equity")] public decimal Equity { get; set; }
    }

    public class Ledger
    {
        [JsonPropertyName("currency")] public string Currency { get; set; } = "KRW";
        [JsonPropertyName("cash")] public decimal Cash { get; set; }
        [JsonPropertyName("commission_rate")] public decimal CommissionRate { get; set; } = 0.00015m;
        [JsonPropertyName("slippage_ticks")] public int SlippageTicks { get; set; }
        [JsonPropertyName("holdings")] public SortedDictionary<string, LedgerHolding> Holdings { get; set; } = new();
        [JsonPropertyName("open_orders")] public List<LedgerOrder> OpenOrders { get; set; } = new();
        [JsonPropertyName("next_order_id")] public int NextOrderId { get; set; } = 1;
        [JsonPropertyName("fills")] public List<LedgerFill> Fills { get; set; } = new();
        [JsonPropertyName("events")] public List<LedgerEvent> Events { get; set; } = new();
        [JsonPropertyName("equity")] public List<LedgerEquity> Equity { get; set; } = new();
        [JsonPropertyName("last_session")] public string LastSession { get; set; } = "";
        [JsonPropertyName("broker")] public string Broker { get; set; } = "paper";
        // anything klean adds that this version doesn't know about is kept as it is
        [JsonExtensionData] public Dictionary<string, JsonElement> Extra { get; set; }

        private static readonly JsonSerializerOptions Options = new() { WriteIndented = true };

        public static Ledger Load(string path) => JsonSerializer.Deserialize<Ledger>(File.ReadAllText(path), Options);

        public void Save(string path)
        {
            var tmp = path + ".tmp";
            File.WriteAllText(tmp, JsonSerializer.Serialize(this, Options));
            File.Move(tmp, path, true);
        }
    }

    /// <summary>A day's prices of one stock, in won (the files store them x10000).</summary>
    public record DailyBar(DateTime Date, decimal Open, decimal High, decimal Low, decimal Close, decimal Volume);

    /// <summary>Reads klean's daily KRX files (data/equity/krx/daily/&lt;code&gt;.zip).</summary>
    public static class KrxDailyFiles
    {
        public static DailyBar Read(string dataFolder, string code, DateTime date)
        {
            var path = Path.Combine(dataFolder, "equity", "krx", "daily", code.ToLowerInvariant() + ".zip");
            if (!File.Exists(path)) return null;
            var key = date.ToString("yyyyMMdd", CultureInfo.InvariantCulture);
            using var zip = ZipFile.OpenRead(path);
            using var reader = new StreamReader(zip.Entries[0].Open());
            string line;
            while ((line = reader.ReadLine()) != null)
            {
                if (!line.StartsWith(key, StringComparison.Ordinal)) continue;
                var c = line.Split(',');
                decimal P(int i) => decimal.Parse(c[i], CultureInfo.InvariantCulture) / 10000m;
                return new DailyBar(date, P(1), P(2), P(3), P(4), decimal.Parse(c[5], CultureInfo.InvariantCulture));
            }
            return null;
        }

        /// <summary>KRX trading days, from the KOSPI index file (every trading day has a level).</summary>
        public static List<DateTime> TradingDays(string dataFolder)
        {
            var path = Path.Combine(dataFolder, "index", "krx", "daily", "kospi.zip");
            var days = new List<DateTime>();
            if (!File.Exists(path)) return days;
            using var zip = ZipFile.OpenRead(path);
            using var reader = new StreamReader(zip.Entries[0].Open());
            string line;
            while ((line = reader.ReadLine()) != null)
            {
                if (line.Length >= 8) days.Add(DateTime.ParseExact(line.Substring(0, 8), "yyyyMMdd", CultureInfo.InvariantCulture));
            }
            return days;
        }

        /// <summary>Settlement day (T+2) of a trade on <paramref name="day"/>; past the data: weekdays.</summary>
        public static DateTime Settlement(List<DateTime> days, DateTime day)
        {
            var later = days.Where(d => d > day).Take(2).ToList();
            var d2 = later.Count == 2 ? later[1] : day;
            for (var added = later.Count; added < 2;)
            {
                d2 = d2.AddDays(1);
                if (d2.DayOfWeek != DayOfWeek.Saturday && d2.DayOfWeek != DayOfWeek.Sunday) added++;
            }
            return d2;
        }
    }
}
