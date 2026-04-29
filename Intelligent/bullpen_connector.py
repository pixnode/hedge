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
            # Perintah Utama: Ambil data kolektif smart-money
            cmd = f"{cmd_base} polymarket data smart-money --output json"
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            
            if res.returncode != 0:
                return {"score": 0.0, "direction_score": 0.0, "raw": None}
            
            raw_output = res.stdout.strip()
            
            # --- STRATEGI INSPEKSI DATA MENTAH (SESUAI INSTRUKSI) ---
            try:
                debug_path = "debug_bullpen_raw.txt"
                with open(debug_path, "w") as f:
                    f.write(raw_output)
                print(f"DEBUG: Raw Bullpen data dumped to {debug_path} ({len(raw_output)} bytes)")
            except Exception as e:
                print(f"DEBUG: Failed to dump raw data: {e}")
            # -------------------------------------------------------

            if not raw_output:
                return {"score": 0.0, "direction_score": 0.0, "raw": None}
                
            data = json.loads(raw_output)
            return self._parse_v6_deep(data)
            
        except Exception as e:
            logger.error(f"Failed to fetch Bullpen v6: {e}")
            return {"score": 0.0, "direction_score": 0.0, "raw": None}

    def _parse_v6_deep(self, data):
        """
        Parser v6.0: Menunggu hasil inspeksi debug_bullpen_raw.txt.
        Saat ini menggunakan logika pencarian kata kunci yang sangat luas.
        """
        try:
            up_votes = 0
            down_votes = 0
            
            signals = data.get("signals", []) if isinstance(data, dict) else []
            
            for s in signals:
                title = str(s.get("title", "")).upper()
                summary = str(s.get("summary", "")).upper()
                text = title + " " + summary
                
                # Keywords Pencarian Arah
                is_up = any(k in text for k in ["UP", "BULLISH", "LONG", "YES", "BUY"])
                is_down = any(k in text for k in ["DOWN", "BEARISH", "SHORT", "NO", "SELL"])
                
                if is_up: up_votes += 1
                if is_down: down_votes += 1
                
            total = up_votes + down_votes
            direction_score = 0.0
            if total > 0:
                direction_score = (up_votes - down_votes) / total
                
            return {
                "score": round(direction_score, 2),
                "direction_score": round(direction_score, 2),
                "total_votes": total,
                "raw": data
            }
        except Exception as e:
            logger.error(f"Error in Bullpen v6 Parser: {e}")
            return {"score": 0.0, "direction_score": 0.0, "raw": data}
