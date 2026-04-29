import random
import json
import statistics
import csv
import os

class ATSBacktesterV3:
    def __init__(self, target_max_entry=0.35, max_hedge_cost=0.90):
        self.target_max_entry = target_max_entry
        self.max_hedge_cost = max_hedge_cost
        self.initial_balance = 1000.0
        self.balance = self.initial_balance
        self.trade_size = 10.0 # $10 per trade
        
        # Results tracking
        self.trades = []
        self.win_count = 0
        self.loss_count = 0
        self.skipped_count = 0
        
    def run_simulation(self, iterations=1000):
        print(f"--- Starting Backtest (1000 Trades) ---")
        print(f"Parameters: TargetMaxEntry={self.target_max_entry}, MaxHedge={self.max_hedge_cost}\n")
        
        for i in range(iterations):
            # Generate Synthetic Market Conditions
            # 1. Market Move (UP/DOWN) - True Outcome
            outcome = random.choice(["UP", "DOWN"])
            
            # 2. Indicators (CVD, OB, Bullpen)
            cvd = random.uniform(-1, 1)
            ob_imbalance = random.uniform(-0.5, 0.5)
            bullpen_sentiment = random.uniform(-1, 1)
            
            # 3. Intelligent Gate Decision Logic (Simplified for simulation)
            confidence = (abs(cvd) * 0.4) + (abs(ob_imbalance) * 0.3) + (abs(bullpen_sentiment) * 0.3)
            
            # Logic: If high confidence AND (CVD matches Bullpen), then ENTER
            is_bullish = cvd > 0.1 and bullpen_sentiment > 0.1
            is_bearish = cvd < -0.1 and bullpen_sentiment < -0.1
            
            decision = "SKIP"
            if confidence > 0.45: # Base threshold
                if is_bullish or is_bearish:
                    decision = "ENTER"
            
            # 4. If ENTER, check Cost Constraints
            if decision == "ENTER":
                # Simulated hedge cost and entry price
                entry_cost = random.uniform(0.10, 0.50)
                hedge_cost = random.uniform(0.60, 0.95)
                
                # Apply User Constraints
                if entry_cost > self.target_max_entry or hedge_cost > self.max_hedge_cost:
                    decision = "SKIP (Cost Violation)"
                    self.skipped_count += 1
                else:
                    # TRADE EXECUTION
                    prediction = "UP" if is_bullish else "DOWN"
                    is_win = prediction == outcome
                    
                    if is_win:
                        # Profit = TradeSize * (1 - costs) -> Simplified payout
                        profit = self.trade_size * (1.0 - entry_cost)
                        self.balance += profit
                        self.win_count += 1
                    else:
                        # Loss = TradeSize * entry_cost -> Total loss in worst case
                        loss = self.trade_size * (entry_cost + (1 - hedge_cost))
                        self.balance -= loss
                        self.loss_count += 1
                    
                    self.trades.append(self.balance)
            else:
                self.skipped_count += 1

    def report_audit(self):
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0
        total_pnl = self.balance - self.initial_balance
        roi = (total_pnl / self.initial_balance) * 100
        
        # Drawdown calculation
        max_dd = 0
        peak = self.initial_balance
        for b in self.trades:
            if b > peak: peak = b
            dd = (peak - b) / peak * 100
            if dd > max_dd: max_dd = dd

        # SAVE TO CSV
        csv_file = "Intelligent/backtest_results.csv"
        with open(csv_file, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["TradeID", "Decision", "Confidence", "Result", "Balance"])
            # Note: In a real scenario we'd track every window, 
            # here we track based on the balances recorded.
            for idx, b in enumerate(self.trades):
                writer.writerow([idx+1, "ENTER", "N/A", "N/A", f"{b:.2f}"])
        
        print(f"\n[OK] Audit File Created: {csv_file}")
        print(f"--- BACKTEST AUDIT REPORT ---")
        print(f"Total Windows: 1000")
        print(f"Decisions: ENTER={total_trades}, SKIP={self.skipped_count}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Final Balance: ${self.balance:.2f}")
        print(f"Total PnL: ${total_pnl:.2f} ({roi:.2f}%)")
        print(f"Max Drawdown: {max_dd:.2f}%")
        print(f"Profit Factor: {abs(self.win_count/self.loss_count) if self.loss_count > 0 else 'inf'}")
        print(f"-----------------------------")

if __name__ == "__main__":
    backtester = ATSBacktesterV3(target_max_entry=0.35, max_hedge_cost=0.90)
    backtester.run_simulation(1000)
    backtester.report_audit()
