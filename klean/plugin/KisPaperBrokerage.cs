/*
 * klean's KIS-PAPER brokerage (config "live-mode-brokerage": "KisPaperBrokerage"): the strategy's
 * orders go to a Korea Investment & Securities 모의투자 (paper) account, never a real one (see
 * KisClient). A daily run
 * processes trading day T (config "krx-session-date") during KRX's pre-open auction of the next
 * trading day (08:30-08:59 KST): market orders join the opening auction and fill at the open.
 *
 * At the start of a run: the fills of orders sent on earlier runs are read from KIS into the
 * ledger, and the account (cash after T+2 settlement, holdings) comes from KIS. Orders are sent
 * only inside the pre-open window (config "krx-kis-any-time": true allows any time, for testing
 * a 모의투자 account during market hours, when market orders fill at once).
 */
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using QuantConnect.Brokerages;
using QuantConnect.Configuration;
using QuantConnect.Interfaces;
using QuantConnect.Logging;
using QuantConnect.Orders;
using QuantConnect.Orders.Fees;
using QuantConnect.Packets;
using QuantConnect.Securities;

namespace QuantConnect.Krx
{
    public class KisPaperBrokerage : Brokerage
    {
        private static readonly TimeZoneInfo Kst = TimeZoneInfo.CreateCustomTimeZone("KST", TimeSpan.FromHours(9), "KST", "KST");
        private readonly IAlgorithm _algorithm;
        private readonly string _ledgerPath = Config.Get("krx-ledger");
        private readonly bool _anyTime = Config.GetBool("krx-kis-any-time", false);
        private readonly object _lock = new();
        private KisClient _kis;
        private Ledger _ledger;
        private KisBalance _balance;
        private string _sessionKey;
        private bool _connected;

        public KisPaperBrokerage(IAlgorithm algorithm) : base("KisPaperBrokerage") { _algorithm = algorithm; }

        public override bool IsConnected => _connected;
        public override string AccountBaseCurrency => "KRW";

        /// <summary>Korean time; KLEAN_KIS_NOW ("2026-10-02T08:35") fixes it, for tests.</summary>
        private static DateTime NowKst
        {
            get
            {
                var fixedTime = Environment.GetEnvironmentVariable("KLEAN_KIS_NOW");
                return string.IsNullOrEmpty(fixedTime) ? TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, Kst)
                    : DateTime.Parse(fixedTime, CultureInfo.InvariantCulture);
            }
        }

        /// <summary>KRX's pre-open auction, when orders join the opening price: 08:30 to 08:59 KST.</summary>
        public static bool InPreOpen(DateTime kst) => kst.TimeOfDay >= new TimeSpan(8, 30, 0) && kst.TimeOfDay < new TimeSpan(8, 59, 30);

        public override void Connect()
        {
            if (_connected) return;
            _kis = KrxSession.Kis;
            _sessionKey = KrxSession.Date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            lock (_lock)
            {
                _ledger = Ledger.Load(_ledgerPath);
                if (_ledger.LastSession != "" && string.CompareOrdinal(_sessionKey, _ledger.LastSession) <= 0)
                {
                    throw new InvalidOperationException($"KisPaperBrokerage: {_sessionKey} was already processed (ledger at {_ledger.LastSession})");
                }
                ReadFills();
                _balance = _kis.Balance();
                _ledger.Cash = _balance.Cash;
                _ledger.Holdings = new SortedDictionary<string, LedgerHolding>(_balance.Holdings.ToDictionary(
                    h => h.Code, h => new LedgerHolding { Quantity = h.Quantity, AveragePrice = h.AveragePrice }));
                var held = _balance.Holdings.Sum(h => h.Quantity * (KrxDailyFiles.Read(KrxSession.DataFolder, h.Code, KrxSession.Date)?.Close ?? h.Price));
                _ledger.Equity.RemoveAll(e => e.Session == _sessionKey);
                _ledger.Equity.Add(new LedgerEquity { Session = _sessionKey, Cash = _balance.Cash, HoldingsValue = held, Equity = _balance.Cash + held });
                _ledger.LastSession = _sessionKey;
                _ledger.Broker = "kis-paper";
                _ledger.Save(_ledgerPath);
            }
            _connected = true;
            KrxSession.Touch();
            KrxSession.StopWhenDone(_algorithm, () => _connected, "KisPaperBrokerage");
            Log.Trace($"KisPaperBrokerage (KIS-PAPER, 모의투자): session {_sessionKey}, cash {_balance.Cash:N0}, {_balance.Holdings.Count} holdings");
        }

        public override void Disconnect() => _connected = false;

        /// <summary>Fills of the orders earlier runs sent, from KIS; orders end with their day.</summary>
        private void ReadFills()
        {
            var sent = _ledger.OpenOrders.Where(o => !string.IsNullOrEmpty(o.KisOrderNo)).ToList();
            if (sent.Count == 0) return;
            var today = NowKst.ToString("yyyyMMdd", CultureInfo.InvariantCulture);
            var from = sent.Min(o => o.SentDate);
            var executions = _kis.Executions(from, today).ToDictionary(e => e.OrderNo.TrimStart('0'), e => e);
            foreach (var o in sent)
            {
                executions.TryGetValue(o.KisOrderNo.TrimStart('0'), out var e);
                var finished = string.CompareOrdinal(o.SentDate, today) < 0 || e == null || e.Remaining == 0 || e.Canceled;
                if (e != null && e.FilledQuantity > 0 && !_ledger.Fills.Any(f => f.OrderId == o.Id))
                {
                    _ledger.Fills.Add(new LedgerFill
                    {
                        OrderId = o.Id, Session = _sessionKey, Symbol = o.Symbol,          // filled at this day's open
                        Quantity = Math.Sign(o.Quantity) * e.FilledQuantity, Price = e.AveragePrice, Type = o.Type, Tag = o.Tag,
                    });
                    Log.Trace($"KisPaperBrokerage: order {o.Id} (KIS {o.KisOrderNo}) {o.Symbol} filled {e.FilledQuantity:N0} @ {e.AveragePrice:N0}");
                }
                if (!finished) continue;
                _ledger.OpenOrders.Remove(o);
                var unfilled = Math.Abs(o.Quantity) - (e?.FilledQuantity ?? 0);
                if (unfilled > 0)
                {
                    _ledger.Events.Add(new LedgerEvent { OrderId = o.Id, Session = _sessionKey, Symbol = o.Symbol,
                        Status = e == null ? "unknown" : e.Canceled ? "canceled" : e.Rejected > 0 ? "rejected" : "expired",
                        Message = e == null ? "KIS doesn't list this order" : $"{unfilled:N0} of {Math.Abs(o.Quantity):N0} shares not filled" });
                }
            }
        }

        public override List<CashAmount> GetCashBalance() => new() { new CashAmount(_balance.Cash, "KRW") };

        public override List<Holding> GetAccountHoldings() => _balance.Holdings.Select(h => new Holding
        {
            Symbol = Symbol.Create(h.Code, SecurityType.Equity, "krx"), Quantity = h.Quantity,
            AveragePrice = h.AveragePrice, MarketPrice = h.Price, CurrencySymbol = "₩",
        }).ToList();

        public override List<Order> GetOpenOrders() => new();      // KIS day orders: none survive to the next pre-open

        public override bool PlaceOrder(Order order)
        {
            KrxSession.Touch();
            string why = null;
            if (order.Type is not (OrderType.Market or OrderType.MarketOnOpen or OrderType.Limit))
                why = $"{order.Type} orders aren't supported with KIS (Market, MarketOnOpen, Limit)";
            else if (order.Quantity != Math.Truncate(order.Quantity))
                why = "KRX shares trade in whole numbers";
            else if (!_anyTime && !InPreOpen(NowKst))
                why = $"orders go to KIS only during the pre-open auction (08:30-08:59 KST); it's {NowKst:HH:mm} KST";
            if (why != null)
            {
                OnOrderEvent(new OrderEvent(order, DateTime.UtcNow, OrderFee.Zero, why) { Status = OrderStatus.Invalid });
                return false;
            }
            KisOrderResult result;
            try
            {
                result = _kis.Order(order.Symbol.Value, order.Quantity, (order as LimitOrder)?.LimitPrice);
            }
            catch (Exception e)
            {
                Log.Error($"KisPaperBrokerage: order {order.Symbol} {order.Quantity}: {e.Message}");
                lock (_lock)
                {
                    _ledger.Events.Add(new LedgerEvent { OrderId = 0, Session = _sessionKey, Symbol = order.Symbol.Value, Status = "rejected", Message = e.Message });
                    _ledger.Save(_ledgerPath);
                }
                OnOrderEvent(new OrderEvent(order, DateTime.UtcNow, OrderFee.Zero, e.Message) { Status = OrderStatus.Invalid });
                return false;
            }
            lock (_lock)
            {
                var id = _ledger.NextOrderId++;
                _ledger.OpenOrders.Add(new LedgerOrder
                {
                    Id = id, Symbol = order.Symbol.Value, Type = order.Type == OrderType.Limit ? "Limit" : "Market",
                    Quantity = order.Quantity, LimitPrice = (order as LimitOrder)?.LimitPrice, PlacedSession = _sessionKey,
                    PlacedUtc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture), Tag = order.Tag ?? "",
                    KisOrderNo = result.OrderNo, KisBranchNo = result.BranchNo, SentDate = NowKst.ToString("yyyyMMdd", CultureInfo.InvariantCulture),
                });
                _ledger.Save(_ledgerPath);
            }
            order.BrokerId.Add(result.OrderNo);
            Log.Trace($"KisPaperBrokerage: sent {order.Symbol} {order.Quantity:N0} {(order is LimitOrder l ? "limit " + l.LimitPrice : "market")} -> KIS order {result.OrderNo}");
            OnOrderEvent(new OrderEvent(order, DateTime.UtcNow, OrderFee.Zero, $"sent to KIS (order {result.OrderNo})") { Status = OrderStatus.Submitted });
            return true;
        }

        public override bool UpdateOrder(Order order)
        {
            OnOrderEvent(new OrderEvent(order, DateTime.UtcNow, OrderFee.Zero, "updating orders isn't supported: cancel and place a new one")
                { Status = OrderStatus.Invalid });
            return false;
        }

        public override bool CancelOrder(Order order)
        {
            KrxSession.Touch();
            LedgerOrder sent;
            lock (_lock) sent = _ledger.OpenOrders.FirstOrDefault(o => order.BrokerId.Contains(o.KisOrderNo));
            if (sent == null) return false;
            try
            {
                _kis.Cancel(sent.KisOrderNo, sent.KisBranchNo);
            }
            catch (Exception e)
            {
                Log.Error($"KisPaperBrokerage: cancel {sent.KisOrderNo}: {e.Message}");
                return false;
            }
            OnOrderEvent(new OrderEvent(order, DateTime.UtcNow, OrderFee.Zero) { Status = OrderStatus.CancelPending });
            return true;
        }
    }

    public class KisPaperBrokerageFactory : BrokerageFactory
    {
        public KisPaperBrokerageFactory() : base(typeof(KisPaperBrokerage)) { }
        public override Dictionary<string, string> BrokerageData => new();
        public override IBrokerageModel GetBrokerageModel(IOrderProvider orderProvider) => new DefaultBrokerageModel(AccountType.Cash);
        public override IBrokerage CreateBrokerage(LiveNodePacket job, IAlgorithm algorithm) => new KisPaperBrokerage(algorithm);
        public override void Dispose() { }
    }
}
