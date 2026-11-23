/*
 * klean's KRX paper brokerage for daily live runs (LEAN live mode, config
 * "live-mode-brokerage": "KrxPaperBrokerage"). The account lives in a ledger file (config
 * "krx-ledger") between runs; each run is one trading day (config "krx-session-date").
 *
 * At the start of a run, orders left by earlier runs are filled at this day's open (market
 * orders) or close (market-on-close), or at their limit when the day's range reaches it, with
 * KRX commission, the sell-side tax by settlement date (T+2) and slippage in KRX ticks: the
 * same rules as the KRX models in backtests. Then LEAN is given the account (cash, holdings,
 * the orders still waiting), so the strategy sees its fills before it decides anything. Orders
 * it places are kept for the next trading day. The run ends by itself once the day's data has
 * been processed and no order has come in for a few seconds.
 */
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Threading;
using QuantConnect.Brokerages;
using QuantConnect.Configuration;
using QuantConnect.Interfaces;
using QuantConnect.Logging;
using QuantConnect.Orders;
using QuantConnect.Orders.Fees;
using QuantConnect.Packets;
using QuantConnect.Securities;
using KrxBoards = QuantConnect.Algorithm.CSharp.KrxBoards;
using KrxFeeModel = QuantConnect.Algorithm.CSharp.KrxFeeModel;
using KrxPriceVariationModel = QuantConnect.Algorithm.CSharp.KrxPriceVariationModel;

namespace QuantConnect.Krx
{
    public class KrxPaperBrokerage : Brokerage
    {
        private readonly IAlgorithm _algorithm;
        private readonly string _ledgerPath = Config.Get("krx-ledger");
        private readonly double _quietSeconds = Config.GetDouble("krx-quiet-seconds", 5);
        private readonly double _maxSeconds = Config.GetDouble("krx-max-seconds", 600);
        private readonly object _lock = new();
        private Ledger _ledger;
        private DateTime _session;
        private string _sessionKey;
        private Dictionary<string, string> _boards;
        private List<DateTime> _days;
        private bool _connected;
        private Thread _watcher;

        public KrxPaperBrokerage(IAlgorithm algorithm) : base("KrxPaperBrokerage")
        {
            _algorithm = algorithm;
        }

        public override bool IsConnected => _connected;
        public override string AccountBaseCurrency => "KRW";

        public override void Connect()
        {
            if (_connected) return;
            if (string.IsNullOrEmpty(_ledgerPath)) throw new InvalidOperationException("KrxPaperBrokerage: config krx-ledger is not set");
            _session = KrxSession.Date;
            _sessionKey = _session.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            _boards = KrxBoards.Load(KrxSession.DataFolder);
            _days = KrxDailyFiles.TradingDays(KrxSession.DataFolder);
            lock (_lock)
            {
                _ledger = Ledger.Load(_ledgerPath);
                if (string.CompareOrdinal(_sessionKey, _ledger.LastSession) <= 0 && _ledger.LastSession != "")
                {
                    throw new InvalidOperationException($"KrxPaperBrokerage: {_sessionKey} was already processed (ledger at {_ledger.LastSession})");
                }
                FillWaitingOrders();
                RecordEquity();
                _ledger.LastSession = _sessionKey;
                _ledger.Save(_ledgerPath);
            }
            _connected = true;
            KrxSession.Touch();
            _watcher = new Thread(Watch) { IsBackground = true, Name = "KrxPaperBrokerage watcher" };
            _watcher.Start();
            Log.Trace($"KrxPaperBrokerage: session {_sessionKey}, cash {_ledger.Cash:N0}, {_ledger.Holdings.Count} holdings, {_ledger.OpenOrders.Count} waiting orders");
        }

        public override void Disconnect()
        {
            _connected = false;
        }

        // ------------------------------------------------------------ the account for LEAN

        public override List<CashAmount> GetCashBalance()
        {
            lock (_lock) return new List<CashAmount> { new CashAmount(_ledger.Cash, "KRW") };
        }

        public override List<Holding> GetAccountHoldings()
        {
            lock (_lock)
            {
                return _ledger.Holdings.Select(h =>
                {
                    var price = KrxDailyFiles.Read(KrxSession.DataFolder, h.Key, _session)?.Close ?? h.Value.AveragePrice;
                    return new Holding
                    {
                        Symbol = Symbol.Create(h.Key, SecurityType.Equity, "krx"),
                        Quantity = h.Value.Quantity,
                        AveragePrice = h.Value.AveragePrice,
                        MarketPrice = price,
                        CurrencySymbol = "₩",
                    };
                }).ToList();
            }
        }

        public override List<Order> GetOpenOrders()
        {
            lock (_lock)
            {
                var time = DateTime.UtcNow;
                return _ledger.OpenOrders.Select(o =>
                {
                    var symbol = Symbol.Create(o.Symbol, SecurityType.Equity, "krx");
                    Order order = o.Type switch
                    {
                        "Limit" => new LimitOrder(symbol, o.Quantity, o.LimitPrice ?? 0m, time, o.Tag),
                        "MarketOnClose" => new MarketOnCloseOrder(symbol, o.Quantity, time, o.Tag),
                        "MarketOnOpen" => new MarketOnOpenOrder(symbol, o.Quantity, time, o.Tag),
                        _ => new MarketOrder(symbol, o.Quantity, time, o.Tag),
                    };
                    order.BrokerId.Add(o.Id.ToString(CultureInfo.InvariantCulture));
                    return order;
                }).ToList();
            }
        }

        // ------------------------------------------------------------ orders from the strategy

        public override bool PlaceOrder(Order order)
        {
            KrxSession.Touch();
            var type = order.Type switch
            {
                OrderType.Market => "Market",
                OrderType.MarketOnOpen => "MarketOnOpen",
                OrderType.MarketOnClose => "MarketOnClose",
                OrderType.Limit => "Limit",
                _ => null,
            };
            if (type == null || order.Quantity != Math.Truncate(order.Quantity))
            {
                var why = type == null ? $"{order.Type} orders aren't supported (Market, MarketOnOpen, MarketOnClose, Limit)"
                    : "KRX shares trade in whole numbers";
                OnOrderEvent(new OrderEvent(order, DateTime.UtcNow, OrderFee.Zero, why) { Status = OrderStatus.Invalid });
                return false;
            }
            int id;
            lock (_lock)
            {
                id = _ledger.NextOrderId++;
                _ledger.OpenOrders.Add(new LedgerOrder
                {
                    Id = id, Symbol = order.Symbol.Value, Type = type, Quantity = order.Quantity,
                    LimitPrice = (order as LimitOrder)?.LimitPrice, PlacedSession = _sessionKey,
                    PlacedUtc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture), Tag = order.Tag ?? "",
                });
                _ledger.Save(_ledgerPath);
            }
            order.BrokerId.Add(id.ToString(CultureInfo.InvariantCulture));
            OnOrderEvent(new OrderEvent(order, DateTime.UtcNow, OrderFee.Zero,
                "waiting for the next trading day (klean paper)") { Status = OrderStatus.Submitted });
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
            lock (_lock)
            {
                var ids = order.BrokerId.Select(b => int.TryParse(b, out var i) ? i : -1).ToHashSet();
                var waiting = _ledger.OpenOrders.Where(o => ids.Contains(o.Id)).ToList();
                if (waiting.Count == 0) return false;
                foreach (var o in waiting)
                {
                    _ledger.OpenOrders.Remove(o);
                    _ledger.Events.Add(new LedgerEvent { OrderId = o.Id, Session = _sessionKey, Symbol = o.Symbol, Status = "canceled", Message = "canceled by the strategy" });
                }
                _ledger.Save(_ledgerPath);
            }
            OnOrderEvent(new OrderEvent(order, DateTime.UtcNow, OrderFee.Zero) { Status = OrderStatus.Canceled });
            return true;
        }

        // ------------------------------------------------------------ filling waiting orders

        private decimal Tick(string board, decimal price) => KrxPriceVariationModel.Tick(board, _session, price);

        private void FillWaitingOrders()
        {
            foreach (var o in _ledger.OpenOrders.ToList())
            {
                if (string.CompareOrdinal(o.PlacedSession, _sessionKey) >= 0) continue;
                var bar = KrxDailyFiles.Read(KrxSession.DataFolder, o.Symbol, _session);
                if (bar == null)
                {
                    Log.Trace($"KrxPaperBrokerage: {o.Symbol} didn't trade on {_sessionKey}; order {o.Id} keeps waiting");
                    continue;
                }
                var board = _boards.TryGetValue(o.Symbol, out var b) ? b : KrxBoards.Kospi;
                var buy = o.Quantity > 0;
                decimal? price = o.Type switch
                {
                    "MarketOnClose" => bar.Close,
                    "Limit" when buy => bar.Open <= o.LimitPrice ? bar.Open : bar.Low <= o.LimitPrice ? o.LimitPrice : null,
                    "Limit" => bar.Open >= o.LimitPrice ? bar.Open : bar.High >= o.LimitPrice ? o.LimitPrice : null,
                    _ => bar.Open,
                };
                if (price == null) continue;                       // limit not reached: keeps waiting
                var fill = price.Value;
                if (o.Type != "Limit" && _ledger.SlippageTicks > 0)
                {
                    var slip = _ledger.SlippageTicks * Tick(board, fill);
                    fill = buy ? fill + slip : Math.Max(fill - slip, Tick(board, fill));
                }
                var quantity = o.Quantity;
                _ledger.OpenOrders.Remove(o);
                if (!buy)
                {
                    var held = _ledger.Holdings.TryGetValue(o.Symbol, out var h) ? h.Quantity : 0m;
                    if (held <= 0)
                    {
                        _ledger.Events.Add(new LedgerEvent { OrderId = o.Id, Session = _sessionKey, Symbol = o.Symbol, Status = "rejected", Message = "nothing to sell (no short selling)" });
                        continue;
                    }
                    quantity = Math.Max(quantity, -held);
                }
                else
                {
                    var affordable = Math.Floor(_ledger.Cash / (fill * (1 + _ledger.CommissionRate)));
                    if (affordable < quantity)
                    {
                        _ledger.Events.Add(new LedgerEvent { OrderId = o.Id, Session = _sessionKey, Symbol = o.Symbol, Status = "reduced",
                            Message = $"cash for {affordable:N0} of {quantity:N0} shares at {fill:N0}" });
                        quantity = affordable;
                    }
                    if (quantity <= 0) continue;
                }
                var value = Math.Abs(quantity) * fill;
                var commission = Math.Floor(value * _ledger.CommissionRate);
                var tax = buy ? 0m : Math.Floor(value * KrxFeeModel.SellTaxRate(board, KrxDailyFiles.Settlement(_days, _session)));
                _ledger.Cash -= quantity * fill + commission + tax;
                var position = _ledger.Holdings.TryGetValue(o.Symbol, out var p) ? p : new LedgerHolding();
                if (buy)
                {
                    position.AveragePrice = (position.Quantity * position.AveragePrice + quantity * fill) / (position.Quantity + quantity);
                }
                position.Quantity += quantity;
                if (position.Quantity == 0) _ledger.Holdings.Remove(o.Symbol);
                else _ledger.Holdings[o.Symbol] = position;
                _ledger.Fills.Add(new LedgerFill
                {
                    OrderId = o.Id, Session = _sessionKey, Symbol = o.Symbol, Quantity = quantity, Price = fill,
                    Commission = commission, Tax = tax, Type = o.Type, Tag = o.Tag,
                });
                Log.Trace($"KrxPaperBrokerage: filled order {o.Id} {o.Symbol} {quantity:N0} @ {fill:N0} (commission {commission:N0}, tax {tax:N0})");
            }
        }

        private void RecordEquity()
        {
            var holdings = 0m;
            foreach (var h in _ledger.Holdings)
            {
                var close = KrxDailyFiles.Read(KrxSession.DataFolder, h.Key, _session)?.Close
                    ?? LastClose(h.Key) ?? h.Value.AveragePrice;
                holdings += h.Value.Quantity * close;
            }
            _ledger.Equity.RemoveAll(e => e.Session == _sessionKey);
            _ledger.Equity.Add(new LedgerEquity { Session = _sessionKey, Cash = _ledger.Cash, HoldingsValue = holdings, Equity = _ledger.Cash + holdings });
        }

        private decimal? LastClose(string code)
        {
            foreach (var day in _days.Where(d => d < _session).Reverse().Take(30))
            {
                var bar = KrxDailyFiles.Read(KrxSession.DataFolder, code, day);
                if (bar != null) return bar.Close;
            }
            return null;
        }

        // ------------------------------------------------------------ ending the run

        private void Watch()
        {
            var started = DateTime.UtcNow;
            while (_connected)
            {
                Thread.Sleep(500);
                var quiet = (DateTime.UtcNow - KrxSession.LastActivityUtc).TotalSeconds;
                var elapsed = (DateTime.UtcNow - started).TotalSeconds;
                var delivered = !KrxSession.Delivered.IsEmpty;
                if ((delivered && quiet >= _quietSeconds) || elapsed >= _maxSeconds)
                {
                    Log.Trace($"KrxPaperBrokerage: session {_sessionKey} done ({(delivered ? "data processed" : "no data within the time limit")}), stopping");
                    _algorithm.Debug($"klean: KRX session {_sessionKey} done");
                    _algorithm.SetStatus(AlgorithmStatus.Stopped);
                    return;
                }
            }
        }
    }

    public class KrxPaperBrokerageFactory : BrokerageFactory
    {
        public KrxPaperBrokerageFactory() : base(typeof(KrxPaperBrokerage)) { }
        public override Dictionary<string, string> BrokerageData => new();
        public override IBrokerageModel GetBrokerageModel(IOrderProvider orderProvider) => new DefaultBrokerageModel(AccountType.Cash);
        public override IBrokerage CreateBrokerage(LiveNodePacket job, IAlgorithm algorithm) => new KrxPaperBrokerage(algorithm);
        public override void Dispose() { }
    }
}
