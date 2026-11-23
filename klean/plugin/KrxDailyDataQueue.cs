/*
 * Live data for klean's daily KRX runs: each LEAN live run processes one trading day (the
 * "session", config "krx-session-date", yyyy-MM-dd) and this feed delivers that day's bar of
 * every KRX equity the strategy subscribes to at daily resolution, from klean's daily files.
 * Finer resolutions get nothing (there is no intraday KRX data).
 */
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Globalization;
using QuantConnect.Configuration;
using QuantConnect.Data;
using QuantConnect.Data.Market;
using QuantConnect.Interfaces;
using QuantConnect.Logging;
using QuantConnect.Packets;

namespace QuantConnect.Krx
{
    /// <summary>State shared by the feed and the brokerage within one run.</summary>
    public static class KrxSession
    {
        public static DateTime Date => DateTime.ParseExact(Config.Get("krx-session-date"), "yyyy-MM-dd", CultureInfo.InvariantCulture);
        public static string DataFolder => Config.Get("data-folder", Globals.DataFolder);
        public static readonly ConcurrentDictionary<Symbol, DateTime> Delivered = new();
        private static long _lastActivityTicks = DateTime.UtcNow.Ticks;
        public static DateTime LastActivityUtc => new(System.Threading.Interlocked.Read(ref _lastActivityTicks), DateTimeKind.Utc);
        public static void Touch() => System.Threading.Interlocked.Exchange(ref _lastActivityTicks, DateTime.UtcNow.Ticks);

        /// <summary>Day bars the KRX files don't have yet come from KIS (config "krx-kis-prices").</summary>
        public static bool KisPrices => Config.GetBool("krx-kis-prices", false);
        private static readonly Lazy<KisClient> _kis = new(() => new KisClient());
        public static KisClient Kis => _kis.Value;
        public static readonly ConcurrentDictionary<string, string> PriceSource = new();   // code -> "krx" | "kis"

        /// <summary>Ends the run once the day's data was processed and nothing happened for a few
        /// seconds (config krx-quiet-seconds, default 5), or after krx-max-seconds (default 180).</summary>
        public static void StopWhenDone(IAlgorithm algorithm, Func<bool> running, string label)
        {
            var quietSeconds = Config.GetDouble("krx-quiet-seconds", 5);
            var maxSeconds = Config.GetDouble("krx-max-seconds", 180);
            new System.Threading.Thread(() =>
            {
                var started = DateTime.UtcNow;
                while (running())
                {
                    System.Threading.Thread.Sleep(500);
                    var quiet = (DateTime.UtcNow - LastActivityUtc).TotalSeconds;
                    var delivered = !Delivered.IsEmpty;
                    if ((delivered && quiet >= quietSeconds) || (DateTime.UtcNow - started).TotalSeconds >= maxSeconds)
                    {
                        Log.Trace($"{label}: session {Date:yyyy-MM-dd} done ({(delivered ? "data processed" : "no data within the time limit")}), stopping");
                        algorithm.Debug($"klean: KRX session {Date:yyyy-MM-dd} done");
                        algorithm.SetStatus(AlgorithmStatus.Stopped);
                        return;
                    }
                }
            }) { IsBackground = true, Name = label + " watcher" }.Start();
        }
    }

    public class KrxDailyDataQueue : IDataQueueHandler
    {
        public bool IsConnected => true;
        public void SetJob(LiveNodePacket job) { }
        public void Dispose() { }
        public void Unsubscribe(SubscriptionDataConfig dataConfig) { }

        public IEnumerator<BaseData> Subscribe(SubscriptionDataConfig config, EventHandler newDataAvailableHandler)
        {
            if (config.Symbol.SecurityType != SecurityType.Equity || config.Symbol.ID.Market != "krx"
                || config.Type != typeof(TradeBar) || config.Resolution != Resolution.Daily)
            {
                return Empty();
            }
            var day = KrxSession.Date;
            var bar = KrxDailyFiles.Read(KrxSession.DataFolder, config.Symbol.Value, day);
            KrxSession.PriceSource[config.Symbol.Value] = "krx";
            if (bar == null && KrxSession.KisPrices)
            {
                try
                {
                    bar = KrxSession.Kis.GetDailyBar(config.Symbol.Value, day);
                    KrxSession.PriceSource[config.Symbol.Value] = "kis";
                }
                catch (Exception e)
                {
                    Log.Error($"KrxDailyDataQueue: KIS prices for {config.Symbol} on {day:yyyy-MM-dd}: {e.Message}");
                }
            }
            if (bar == null)
            {
                Log.Trace($"KrxDailyDataQueue: no {day:yyyy-MM-dd} bar for {config.Symbol} (not traded that day)");
                KrxSession.Delivered[config.Symbol] = day;
                return Empty();
            }
            var trade = new TradeBar(day, config.Symbol, bar.Open, bar.High, bar.Low, bar.Close, bar.Volume, TimeSpan.FromDays(1));
            Log.Trace($"KrxDailyDataQueue: {config.Symbol} {day:yyyy-MM-dd} O {bar.Open} C {bar.Close}");
            return Deliver(trade, newDataAvailableHandler);
        }

        private static IEnumerator<BaseData> Deliver(TradeBar bar, EventHandler newData)
        {
            newData?.Invoke(null, EventArgs.Empty);
            yield return bar;
            KrxSession.Delivered[bar.Symbol] = bar.Time;
            KrxSession.Touch();
            while (true) yield return null;
        }

        private static IEnumerator<BaseData> Empty()
        {
            while (true) yield return null;
        }
    }
}
