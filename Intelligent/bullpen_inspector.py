import subprocess
import json
import os

def inspect_bullpen():
    print("--- PHASE 1: INSPEKSI DATA MENTAH ---")
    vps_path = "/root/.bullpen/bin/bullpen"
    cmd_base = vps_path if os.path.exists(vps_path) else "bullpen"
    
    # Mencoba perintah smart-money
    cmd = f"{cmd_base} polymarket data smart-money --output json"
    print(f"Menjalankan: {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
    
    if res.returncode == 0:
        raw = res.stdout.strip()
        print(f"Berhasil menarik {len(raw)} bytes.")
        
        # Simpan ke file untuk Anda periksa
        with open("debug_bullpen_raw.txt", "w") as f:
            f.write(raw)
        print("Data mentah telah di-dump ke: debug_bullpen_raw.txt")
        
        # Cek Kata Kunci Kritis
        keywords = ["side", "BUY", "SELL", "YES", "NO", "outcome", "usdSize", "pnl"]
        print("\nHasil Pencarian Kata Kunci:")
        for k in keywords:
            count = raw.count(k)
            print(f" - '{k}': ditemukan {count} kali")
            
        if "signals" in raw:
            try:
                data = json.loads(raw)
                signals = data.get("signals", [])
                if signals:
                    print(f"\nContoh Sinyal Pertama:\n{json.dumps(signals[0], indent=2)}")
            except:
                print("Gagal parsing JSON.")
    else:
        print(f"Error: {res.stderr}")

    print("\n--- PHASE 2: UJI COBA PERINTAH REAL-TIME ---")
    # Mencoba perintah alternatif untuk trade feed (snapshot)
    cmd_alt = f"{cmd_base} polymarket data trades --limit 5 --output json"
    print(f"Mencoba perintah alternatif: {cmd_alt}")
    res_alt = subprocess.run(cmd_alt, shell=True, capture_output=True, text=True, timeout=15)
    
    if res_alt.returncode == 0:
        print("SUKSES! Perintah 'data trades' tersedia.")
        print(res_alt.stdout[:500] + "...")
    else:
        print(f"Gagal: Perintah 'data trades' tidak dikenal atau error.")

if __name__ == "__main__":
    inspect_bullpen()
