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
        self.trade_size = 10.0
        
        # Results tracking
        self.all_windows = [] # To store every single window detail
        self.win_count = 0
        self.loss_count = 0
        self.skipped_count = 0
        
    def run_simulation(self, iterations=1000):
        for i in range(iterations):
            outcome = random.choice(["UP", "DOWN"])
            cvd = random.uniform(-1, 1)
            ob_imbalance = random.uniform(-0.5, 0.5)
            bullpen_sentiment = random.uniform(-1, 1)
            confidence = (abs(cvd) * 0.4) + (abs(ob_imbalance) * 0.3) + (abs(bullpen_sentiment) * 0.3)
            
            is_bullish = cvd > 0.1 and bullpen_sentiment > 0.1
            is_bearish = cvd < -0.1 and bullpen_sentiment < -0.1
            
            decision = "SKIP"
            reason = "Low Confidence"
            result = "NONE"
            pnl = 0.0
            
            if confidence > 0.45:
                if is_bullish or is_bearish:
                    entry_cost = random.uniform(0.10, 0.50)
                    hedge_cost = random.uniform(0.60, 0.95)
                    
                    if entry_cost > self.target_max_entry:
                        decision = "SKIP"
                        reason = f"Entry Cost Too High ({entry_cost:.2f})"
                    elif hedge_cost > self.max_hedge_cost:
                        decision = "SKIP"
                        reason = f"Hedge Cost Too High ({hedge_cost:.2f})"
                    else:
                        decision = "ENTER"
                        prediction = "UP" if is_bullish else "DOWN"
                        reason = f"Pred: {prediction} (Conf: {confidence:.2f})"
                        
                        if prediction == outcome:
                            result = "WIN"
                            pnl = self.trade_size * (1.0 - entry_cost)
                            self.win_count += 1
                        else:
                            result = "LOSS"
                            pnl = -self.trade_size * (entry_cost + (1 - hedge_cost))
                            self.loss_count += 1
                        
                        self.balance += pnl
            
            if decision == "SKIP" and reason == "Low Confidence":
                self.skipped_count += 1
                
            self.all_windows.append({
                "ID": i + 1,
                "Decision": decision,
                "Reason": reason,
                "Result": result,
                "PnL": f"{pnl:.2f}",
                "Balance": f"{self.balance:.2f}"
            })

    def report_audit(self):
        # SAVE TO CSV
        csv_file = "Intelligent/backtest_results.csv"
        with open(csv_file, mode='w', newline='') as f:
            fieldnames = ["ID", "Decision", "Reason", "Result", "PnL", "Balance"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in self.all_windows:
                writer.writerow(row)
        
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0
        
        print(f"\n[OK] Detailed Audit File Created: {csv_file}")
        print(f"--- BACKTEST AUDIT REPORT ---")
        print(f"Total Windows: 1000")
        print(f"Decisions: ENTER={total_trades}, SKIP={1000 - total_trades}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Final Balance: ${self.balance:.2f}")
        print(f"-----------------------------")

if __name__ == "__main__":
    backtester = ATSBacktesterV3(target_max_entry=0.35, max_hedge_cost=0.90)
    backtester.run_simulation(1000)
    backtester.report_audit()
