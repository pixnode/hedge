import subprocess
import json
import logging
import os

logger = logging.getLogger("intelligent.bullpen")

class BullpenConnector:
    def __init__(self, cli_path="bullpen"):
        self.cli_path = cli_path

    def get_smart_money_signals(self):
        vps_path = "/root/.bullpen/bin/bullpen"
        cmd_base = vps_path if os.path.exists(vps_path) else "bullpen"
        
        try:
            # Perintah Dasar: Ambil data smart-money
            cmd = f"{cmd_base} polymarket data smart-money --output json"
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            
            if res.returncode != 0:
                return {"score": 0.0}
            
            raw_output = res.stdout.strip()
            
            # Tetap lakukan dump untuk inspeksi
            with open("debug_bullpen_raw.txt", "w") as f:
                f.write(raw_output)

            if not raw_output:
                return {"score": 0.0}
                
            data = json.loads(raw_output)
            return self._parse_v4_stable(data)
            
        except Exception as e:
            return {"score": 0.0}

    def _parse_v4_stable(self, data):
        """
        Parser v4 Stable: Mencari kata kunci sederhana di title/summary.
        """
        try:
            up_votes = 0
            down_votes = 0
            
            signals = data.get("signals", []) if isinstance(data, dict) else []
            
            for s in signals:
                text = (str(s.get("title", "")) + " " + str(s.get("summary", ""))).upper()
                if any(k in text for k in ["UP", "BULLISH", "LONG", "YES", "BUY"]): up_votes += 1
                if any(k in text for k in ["DOWN", "BEARISH", "SHORT", "NO", "SELL"]): down_votes += 1
                
            total = up_votes + down_votes
            if total > 0:
                score = (up_votes - down_votes) / total
                return {"score": round(score, 2)}
            
            return {"score": 0.0}
        except:
            return {"score": 0.0}
