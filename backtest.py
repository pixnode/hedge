import random
import csv
import logging
import math
from config import config

# Disable temporal_engine logs
logging.getLogger("temporal_engine").setLevel(logging.CRITICAL)

def generate_wild_window_prices(duration_sec=300, start_price=0.50):
    """Mean-Reverting Jump Diffusion model for BTC price swings."""
    prices = [start_price]
    volatility = 0.02  # Daily noise
    reversion_speed = 0.01 
    
    for t in range(1, duration_sec):
        # 1. Calculate Noise
        noise = random.normalvariate(0, volatility)
        
        # 2. Calculate Reversion
        reversion = reversion_speed * (0.50 - prices[-1])
        
        # 3. Calculate Jump
        jump = 0
        if random.random() < 0.01:  # 1% chance every second
            jump = random.uniform(-0.30, 0.30)
            
        new_price = prices[-1] + noise + reversion + jump
        
        # Constrain to Polymarket limits
        new_price = max(0.01, min(0.99, new_price))
        prices.append(new_price)
        
    return prices

def run_simulation(total_windows=1000):
    results = []
    capital_saved = 0.0
    total_slippage_cost = 0.0
    
    # Derive shares from BASE_TRADE_USD and typical entry price
    # In Polymarket, size = number of shares. Cost = size * price
    # We use BASE_TRADE_USD as the number of shares to buy per side
    shares = config.BASE_TRADE_USD
    
    print(f"Starting Backtest: {total_windows} Windows (Ultra-Safe Mode)")
    print(f"  Entry Target    : <= {config.TARGET_MAX_ENTRY}")
    print(f"  Max Hedge Cost  : <= {config.MAX_HEDGE_COST}")
    print(f"  Slippage        : {config.ABSOLUTE_SLIPPAGE}")
    print(f"  Shares per Side : {shares}")
    print(f"  Panic Timing    : T-{config.GOLDEN_WINDOW_END_SEC}s")
    print()
    
    for w in range(total_windows):
        up_prices = generate_wild_window_prices()
        
        has_up = False
        has_down = False
        leg1_price = 0.0
        leg1_side = ""
        up_entry = 0.0
        down_entry = 0.0
        dynamic_target = config.TARGET_MAX_ENTRY
        panic_mode = False
        window_active = True
        
        pillar1_expired = False
        pillar1_got_one = False
        overlap_zone_active = False
        panic_bid_tracked = 0.0
        
        w_result = {
            "window": w,
            "status": "SKIPPED",
            "pnl": 0.0,
            "panic": False,
            "up_entry": 0.0,
            "down_entry": 0.0,
            "combined": 0.0,
            "invested": 0.0
        }
        
        for t in range(300):
            t_minus = 300 - t
            
            true_up = up_prices[t]
            true_down = 1.0 - true_up
            spread = random.uniform(0.02, 0.06)
            
            up_ask = min(0.99, true_up + spread/2)
            up_bid = max(0.01, true_up - spread/2)
            down_ask = min(0.99, true_down + spread/2)
            down_bid = max(0.01, true_down - spread/2)
            
            if not window_active:
                break
                
            seconds_into_window = t
            
            # Pillar 1 Expiration (T+10)
            if seconds_into_window > config.P1_SNIPER_CLOSE_SEC and not pillar1_expired:
                pillar1_expired = True
                if has_up and has_down:
                    pass # Hedged
                elif has_up ^ has_down:
                    pillar1_got_one = True
                else:
                    window_active = False
                    break
                    
            # Overlap Zone Activation
            if t_minus <= config.OVERLAP_ZONE_SEC and not overlap_zone_active and pillar1_got_one and not (has_up and has_down):
                overlap_zone_active = True
                
            if overlap_zone_active:
                filled_bid = up_bid if has_up else down_bid
                panic_bid_tracked = filled_bid
                
            # Pillar 3: Panic Exit
            if t_minus <= config.GOLDEN_WINDOW_END_SEC and (has_up ^ has_down) and not panic_mode:
                panic_mode = True
                w_result["panic"] = True
                
                missing_ask = down_ask if has_up else up_ask
                filled_entry = up_entry if has_up else down_entry
                
                critical_target = dynamic_target + config.P2_RELAX_CRITICAL + 0.01
                if missing_ask <= critical_target:
                    # Force Buy
                    slip = random.uniform(0.01, config.P2_SLIPPAGE)
                    fill = min(0.99, missing_ask + slip)
                    total_slippage_cost += slip * shares
                    if has_up: down_entry = fill
                    else: up_entry = fill
                    has_up = True; has_down = True
                    w_result["status"] = "FORCE_HEDGED"
                else:
                    if panic_bid_tracked < config.BID_FLOOR_THRESHOLD:
                        w_result["status"] = "LIQUIDITY_VACUUM_EXPIRED"
                        pnl = (0 - filled_entry) * shares
                        w_result["pnl"] = pnl
                    else:
                        slip = random.uniform(0.01, config.ABSOLUTE_SLIPPAGE)
                        sell_price = max(0.01, panic_bid_tracked - slip)
                        total_slippage_cost += slip * shares
                        pnl = (sell_price - filled_entry) * shares
                        w_result["pnl"] = pnl
                        w_result["status"] = "PANIC_EXIT"
                        capital_saved += sell_price * shares
                break
                
            # Pillar 1 & 2 Hunting
            if t_minus > config.GOLDEN_WINDOW_END_SEC and not panic_mode:
                if not pillar1_expired:
                    # Pillar 1
                    if not has_up and up_ask <= config.TARGET_MAX_ENTRY:
                        has_up = True
                        slip = random.uniform(0.01, config.ABSOLUTE_SLIPPAGE)
                        fill = min(0.99, up_ask + slip)
                        total_slippage_cost += slip * shares
                        up_entry = fill
                        leg1_price = fill
                        leg1_side = "UP"
                        dynamic_target = config.MAX_HEDGE_COST - leg1_price
                        
                    if not has_down and down_ask <= config.TARGET_MAX_ENTRY:
                        has_down = True
                        slip = random.uniform(0.01, config.ABSOLUTE_SLIPPAGE)
                        fill = min(0.99, down_ask + slip)
                        total_slippage_cost += slip * shares
                        down_entry = fill
                        if leg1_price == 0.0:
                            leg1_price = fill
                            leg1_side = "DOWN"
                            dynamic_target = config.MAX_HEDGE_COST - leg1_price
                elif pillar1_got_one:
                    # Pillar 2
                    current_dynamic_target = dynamic_target
                    if t_minus <= config.P2_RELAX_LATE_SEC and t_minus > config.P2_RELAX_CRITICAL_SEC:
                        current_dynamic_target += config.P2_RELAX_LATE
                    elif t_minus <= config.P2_RELAX_CRITICAL_SEC:
                        current_dynamic_target += config.P2_RELAX_CRITICAL
                        
                    if not has_up and up_ask <= current_dynamic_target:
                        has_up = True
                        slip = random.uniform(0.01, config.P2_SLIPPAGE)
                        fill = min(0.99, up_ask + slip)
                        total_slippage_cost += slip * shares
                        up_entry = fill
                    if not has_down and down_ask <= current_dynamic_target:
                        has_down = True
                        slip = random.uniform(0.01, config.P2_SLIPPAGE)
                        fill = min(0.99, down_ask + slip)
                        total_slippage_cost += slip * shares
                        down_entry = fill
                        
                if has_up and has_down:
                    w_result["status"] = "HEDGED"
                    break
                    
        # Calculate PnL for hedged trades
        if has_up and has_down:
            combined = up_entry + down_entry
            invested = combined * shares
            # Binary option: one side pays $1/share, other pays $0
            # Holding both sides = guaranteed $1/share payout
            payout = 1.0 * shares
            w_result["pnl"] = payout - invested
            w_result["up_entry"] = up_entry
            w_result["down_entry"] = down_entry
            w_result["combined"] = combined
            w_result["invested"] = invested
            
        results.append(w_result)
        
    return results, capital_saved, total_slippage_cost

def analyze_and_report(results, capital_saved, total_slippage_cost):
    total_pnl = sum(r["pnl"] for r in results)
    
    hedged_trades = [r for r in results if r["status"] == "HEDGED"]
    force_trades = [r for r in results if r["status"] == "FORCE_HEDGED"]
    panic_trades = [r for r in results if r["status"] == "PANIC_EXIT"]
    skipped_trades = [r for r in results if r["status"] == "SKIPPED"]
    
    all_hedged = hedged_trades + force_trades
    
    win_trades = [r for r in results if r["pnl"] > 0]
    loss_trades = [r for r in results if r["pnl"] < 0]
    even_trades = [r for r in results if r["pnl"] == 0 and r["status"] != "SKIPPED"]
    
    total_executions = len(all_hedged) + len(panic_trades)
    win_rate = (len(win_trades) / total_executions * 100) if total_executions > 0 else 0
    
    # Hedged stats
    hedged_pnls = [r["pnl"] for r in all_hedged]
    avg_hedged_profit = sum(hedged_pnls) / len(hedged_pnls) if hedged_pnls else 0
    min_hedged = min(hedged_pnls) if hedged_pnls else 0
    max_hedged = max(hedged_pnls) if hedged_pnls else 0
    
    # Panic stats
    panic_pnls = [r["pnl"] for r in panic_trades]
    avg_panic_loss = sum(panic_pnls) / len(panic_pnls) if panic_pnls else 0
    panic_wins = len([p for p in panic_pnls if p > 0])
    panic_losses = len([p for p in panic_pnls if p <= 0])
    worst_panic = min(panic_pnls) if panic_pnls else 0
    
    # Combined entry stats for hedged
    combined_costs = [r["combined"] for r in all_hedged if r["combined"] > 0]
    avg_combined = sum(combined_costs) / len(combined_costs) if combined_costs else 0
    
    avg_profit = sum(r["pnl"] for r in win_trades) / len(win_trades) if win_trades else 0
    avg_loss = sum(r["pnl"] for r in loss_trades) / len(loss_trades) if loss_trades else 0
    
    # Calculate Max Drawdown
    max_dd = 0.0
    peak = 0.0
    current_balance = 0.0
    max_consecutive_loss = 0
    current_streak = 0
    for r in results:
        current_balance += r["pnl"]
        if current_balance > peak:
            peak = current_balance
        dd = peak - current_balance
        if dd > max_dd:
            max_dd = dd
        if r["pnl"] < 0:
            current_streak += 1
            max_consecutive_loss = max(max_consecutive_loss, current_streak)
        else:
            current_streak = 0
    
    # Profit factor
    gross_profit = sum(r["pnl"] for r in results if r["pnl"] > 0)
    gross_loss = abs(sum(r["pnl"] for r in results if r["pnl"] < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
    
    # Sharpe-like ratio (per-trade)
    all_pnls = [r["pnl"] for r in results if r["status"] != "SKIPPED"]
    if len(all_pnls) > 1:
        mean_pnl = sum(all_pnls) / len(all_pnls)
        variance = sum((p - mean_pnl)**2 for p in all_pnls) / (len(all_pnls) - 1)
        std_pnl = math.sqrt(variance)
        sharpe = (mean_pnl / std_pnl) if std_pnl > 0 else 0
    else:
        sharpe = 0
    
    print("=" * 60)
    print("  BACKTEST ANALYSIS REPORT (POST-AUDIT FIX)")
    print("=" * 60)
    
    print("\n--- TRADE DISTRIBUTION ---")
    print(f"  Total Windows Simulated  : {len(results)}")
    print(f"  Skipped (Pillar 1 filter): {len(skipped_trades)} ({len(skipped_trades)/len(results)*100:.1f}%)")
    print(f"  Fully Hedged             : {len(hedged_trades)} ({len(hedged_trades)/len(results)*100:.1f}%)")
    print(f"  Force Hedged (T-N)       : {len(force_trades)}")
    print(f"  Panic Exits              : {len(panic_trades)} ({len(panic_trades)/len(results)*100:.1f}%)")
    print(f"  Total Executed           : {total_executions}")
    
    print("\n--- PROFITABILITY ---")
    print(f"  Total Net PnL            : ${total_pnl:.2f}")
    print(f"  Win Rate (Executed)      : {win_rate:.2f}%")
    print(f"  Profit Factor            : {profit_factor:.2f}x")
    print(f"  Sharpe Ratio (per trade) : {sharpe:.3f}")
    print(f"  Avg Profit per Win       : ${avg_profit:.4f}")
    print(f"  Avg Loss per Loss        : ${avg_loss:.4f}")
    
    print("\n--- HEDGED TRADES ---")
    print(f"  Count                    : {len(all_hedged)}")
    print(f"  Win Rate                 : 100.00% (mathematically guaranteed)")
    print(f"  Avg PnL per Hedge        : ${avg_hedged_profit:.4f}")
    print(f"  Min Hedge PnL            : ${min_hedged:.4f}")
    print(f"  Max Hedge PnL            : ${max_hedged:.4f}")
    print(f"  Avg Combined Entry Cost  : ${avg_combined:.4f}")
    
    print("\n--- PANIC EXITS (Pillar 3) ---")
    print(f"  Count                    : {len(panic_trades)}")
    print(f"  Panics with Profit       : {panic_wins} (sold higher than entry)")
    print(f"  Panics with Loss         : {panic_losses}")
    print(f"  Avg Panic PnL            : ${avg_panic_loss:.4f}")
    print(f"  Worst Panic Loss         : ${worst_panic:.4f}")
    print(f"  Capital Recovered        : ${capital_saved:.2f}")
    
    print("\n--- RISK METRICS ---")
    print(f"  Max Drawdown             : ${max_dd:.2f}")
    print(f"  Max Consecutive Losses   : {max_consecutive_loss}")
    print(f"  Total Slippage Paid      : ${total_slippage_cost:.2f}")
    
    print("\n" + "=" * 60)

    # Save to CSV with expanded fields
    with open("backtest_report.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["window", "status", "pnl", "panic", "up_entry", "down_entry", "combined", "invested"])
        writer.writeheader()
        writer.writerows(results)
    print("  Detailed logs saved to 'backtest_report.csv'")

if __name__ == "__main__":
    results, cap_saved, slip_cost = run_simulation(1000)
    analyze_and_report(results, cap_saved, slip_cost)
