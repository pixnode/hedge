# Asynchronous Temporal Sniper (ATS) v1.0 — ULTRA-SAFE MODE

ATS v1.0 adalah mesin eksekusi High-Frequency Trading (HFT) berbasis 3-Pillar Architecture yang dioptimalkan untuk memburu arbitrase hedging di pasar Polymarket BTC 5-Minute.

## Arsitektur 3-Pillar

| Pillar | Fungsi | Timing |
|---|---|---|
| **Pillar 1** — Double Trap | Entry filter ketat ≤ 0.20, skip jika tidak terpenuhi | T-300 → T-20 |
| **Pillar 2** — Dynamic Hunter | Recalculate Leg 2 target = `0.80 - Leg1_fill` | Setelah Leg 1 fill |
| **Pillar 3** — Emergency Exit | Force Buy atau Panic Sell posisi single-leg | T-20 → T-0 |

## Struktur File

| File | Fungsi |
|---|---|
| `main.py` | Entrypoint utama. Menjalankan WebSocket, engine, dan UI secara paralel |
| `config.py` | Memuat dan casting semua variabel dari `.env` |
| `temporal_engine.py` | Core logic: 3-Pillar state machine, pre-emptive discovery, trade CSV logging |
| `poly_feed.py` | WebSocket L2 feed — tracking best ask & best bid |
| `executor.py` | Thread-safe ClobClient wrapper — support BUY & SELL dengan slippage |
| `ui.py` | Dashboard Rich terminal (live market, inventory, execution log) |
| `backtest.py` | Simulasi 1000 window dengan Mean-Reverting Jump Diffusion |

## Output Files

| File | Deskripsi |
|---|---|
| `trades.csv` | **Log semua trade** (BUY, SELL, SKIP, CYCLE_DONE, FAILED) — untuk Paper & Live |
| `ats_execution.log` | Log eksekusi teks untuk debugging |
| `backtest_report.csv` | Hasil simulasi 1000 window |

### Format `trades.csv`

```csv
timestamp,window_slug,action,side,asset,ref_price,fill_price,shares,up_entry,down_entry,combined,pnl,status,tx_hash,mode
2026-04-27 14:05:01,btc-updown-5m-1714222500,BUY,BUY,UP,0.18,0.19,2.0,0.19,0.0,0,0,FILLED,abc123,LIVE
2026-04-27 14:05:23,btc-updown-5m-1714222500,BUY,BUY,DOWN,0.55,0.56,2.0,0.19,0.56,0,0,FILLED,def456,LIVE
2026-04-27 14:05:23,btc-updown-5m-1714222500,CYCLE_DONE,-,BOTH,0,0,2.0,0.19,0.56,0.75,0.50,HEDGED,-,LIVE
```

Kolom `mode` otomatis diisi `PAPER` atau `LIVE` berdasarkan `PAPER_TRADING_MODE` di `.env`.

---

## Konfigurasi (.env)

Semua parameter tuning ada di file `.env`:

```env
# API Credentials
POLYMARKET_PRIVATE_KEY=your_private_key
POLY_API_KEY=your_api_key
POLY_API_SECRET=your_api_secret
POLY_API_PASSPHRASE=your_passphrase
POLY_PROXY_ADDRESS=your_proxy_address
SIGNATURE_TYPE=2

# Endpoints
POLY_WS_URL=wss://ws-subscriptions-clob.polymarket.com/ws/market
CLOB_HOST=https://clob.polymarket.com

# Strategy Parameters
PAPER_TRADING_MODE=True       # True = Paper, False = Live
TARGET_MAX_ENTRY=0.20         # Max entry price per leg
MAX_HEDGE_COST=0.80           # Max combined cost for both legs
ABSOLUTE_SLIPPAGE=0.10        # Slippage buffer (Marketable Limit Order)

# Temporal
GOLDEN_WINDOW_START_SEC=300   # Window duration (5 min)
GOLDEN_WINDOW_END_SEC=20      # Panic exit trigger timing

# Position Sizing
BASE_TRADE_USD=2.0            # Shares per side
MAX_POSITION_USD=5.0          # Max total position per window

# Telegram Notifications
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

---

## Tutorial Instalasi dan Deploy

### 1. Persiapan VPS (Linux / Ubuntu)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv git -y
```

### 2. Pindahkan File Bot ke VPS

Upload folder `hedge` via SFTP (FileZilla/WinSCP) ke `/root/hedge`.

### 3. Instalasi Dependencies

```bash
cd /root/hedge
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Konfigurasi `.env`

```bash
nano .env
```
Isi sesuai template di atas. Simpan dengan `Ctrl+X`, `Y`, `Enter`.

---

## Cara Menjalankan

### Opsi A: Menjalankan dengan PM2 (Recommended untuk Production)

PM2 adalah process manager yang menjaga bot tetap hidup 24/7, auto-restart jika crash, dan menyediakan monitoring log.

#### Install PM2

```bash
# Install Node.js jika belum ada
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install PM2
sudo npm install -g pm2
```

#### Jalankan Bot dengan PM2

```bash
cd /root/hedge

# Jalankan bot utama (engine + feed, TANPA UI)
pm2 start "venv/bin/python main_headless.py" --name ats-bot

# Atau jika tidak pakai venv:
pm2 start main_headless.py --interpreter python3 --name ats-bot
```

> **PENTING:** PM2 tidak support Rich UI (karena tidak ada terminal interaktif). Gunakan `main_headless.py` untuk PM2 dan jalankan UI secara terpisah (lihat di bawah).

#### Monitoring Bot via PM2

```bash
# Lihat status semua proses
pm2 status

# Lihat log real-time
pm2 logs ats-bot

# Restart bot
pm2 restart ats-bot

# Stop bot
pm2 stop ats-bot

# Auto-start PM2 setelah reboot VPS
pm2 startup
pm2 save
```

#### Menjalankan UI secara Terpisah (opsional)

Jika Anda ingin melihat dashboard saat sedang SSH ke VPS:

```bash
cd /root/hedge
source venv/bin/activate

# Jalankan UI saja (konek ke engine yang sudah jalan via shared state)
python ui_standalone.py
```

Atau gunakan `tmux` untuk UI persistent:

```bash
tmux new -s ats-ui
source venv/bin/activate
python main.py          # Full mode dengan UI
# Detach: Ctrl+B, D
# Reattach: tmux attach -t ats-ui
```

---

### Opsi B: Menjalankan dengan Tmux (Simple)

```bash
# Buat sesi tmux
tmux new -s sniper

# Aktifkan venv dan jalankan (dengan UI)
source venv/bin/activate
python main.py
```

- **Detach** (tinggalkan bot berjalan): `Ctrl+B`, lepas, tekan `D`
- **Reattach** (lihat bot lagi): `tmux attach -t sniper`

---

### Menjalankan UI Saja (Tanpa Trading)

Jika Anda hanya ingin memantau dashboard tanpa engine trading:

```bash
source venv/bin/activate
python -c "
import asyncio
from temporal_engine import TemporalEngine
from poly_feed import PolyWebsocketFeed
from executor import OrderExecutor
from config import config
from ui import UI

async def main():
    queue = asyncio.Queue()
    feed = PolyWebsocketFeed(config.POLY_WS_URL, queue)
    executor = OrderExecutor(config)
    engine = TemporalEngine(queue, feed, executor)
    ui = UI(engine)
    await asyncio.gather(feed.connect_and_listen(), engine.run(), ui.render_ui())

asyncio.run(main())
"
```

> Ini sama persis dengan `python main.py` — UI hanya bisa berjalan bersama engine karena membaca state dari objek engine secara langsung.

---

## Menjalankan Backtest

```bash
source venv/bin/activate
python backtest.py
```

Hasil akan di-print ke terminal dan disimpan ke `backtest_report.csv`.

---

## Monitoring & Analisis

### File Log yang Harus Dipantau

| File | Perintah | Gunanya |
|---|---|---|
| `trades.csv` | `tail -f trades.csv` | Real-time trade feed |
| `ats_execution.log` | `tail -f ats_execution.log` | Debug log |
| PM2 logs | `pm2 logs ats-bot` | Stdout/stderr dari PM2 |

### Analisis Cepat `trades.csv`

```bash
# Hitung total trade hari ini
grep "$(date +%Y-%m-%d)" trades.csv | wc -l

# Lihat semua HEDGED trades
grep "HEDGED" trades.csv

# Lihat semua PANIC_EXIT
grep "PANIC_EXIT" trades.csv

# Hitung total PnL (kolom 12)
awk -F',' 'NR>1 {sum+=$12} END {print "Total PnL: $"sum}' trades.csv
```

---

> **DISCLAIMER:** Bot ini beroperasi di pasar nyata dengan uang sungguhan. Selalu mulai dengan `PAPER_TRADING_MODE=True` untuk memvalidasi koneksi API dan logika eksekusi sebelum beralih ke Live. Pantau `trades.csv` dan `ats_execution.log` secara rutin.

kode python sama sekali:

TARGET_MAX_ENTRY (Batas harga maksimum untuk Leg 1, default: 0.20)
MAX_HEDGE_COST (Batas total biaya maksimum untuk kedua sisi, default: 0.80)
ABSOLUTE_SLIPPAGE (Biaya slippage statis yang ditambahkan/dikurangkan dari harga saat Panic Sell atau Force Buy, default: 0.10)
BASE_TRADE_USD (Ukuran share/jumlah kontrak per transaksi, default: 2.0)
MAX_POSITION_USD (Batas maksimal inventory per window)