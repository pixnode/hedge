# Asynchronous Temporal Sniper (ATS) v1.0

ATS v1.0 adalah mesin eksekusi High-Frequency Trading (HFT) murni berbasis order book asinkron yang dioptimalkan untuk memburu arbitrase (hedging peluang) di pasar Polymarket (khususnya untuk resolusi candle 5-menit).

## Struktur File Utama
1. **`main.py`**: Entrypoint utama. Menggabungkan WebSocket, executor, dan rendering antarmuka UI.
2. **`config.py`**: Mengatur dan *casting* tipe data dari *environment variables*.
3. **`temporal_engine.py`**: Core logic (Hunter Logic, perhitungan T-Minus, proteksi deadlocks, perlindungan hedging probabilitas).
4. **`poly_feed.py`**: Koneksi stateless/stateful WebSocket L2, mendeteksi *phantom spread* atau penarikan likuiditas order book.
5. **`executor.py`**: Berinteraksi secara *thread-safe* dengan ClobClient untuk post order riil ke Mainnet Polygon.
6. **`ui.py`**: UI Dashboard dinamis berbasis terminal menggunakan library `rich`.
7. **`backtest.py`**: Pipeline backtesting mandiri tanpa koneksi API, didesain untuk menyimulasikan slippage dan interlock concurrency hingga 1000 eksekusi.

---

## Tutorial Instalasi dan Deploy di VPS (Linux / Ubuntu)

Saat berpindah dari mesin lokal/Windows ke VPS kosong, sistem memerlukan library ekstensi pihak ketiga. **Anda tidak perlu menjalankan `ui.py` secara terpisah**, ia otomatis di-_render_ saat menjalankan `main.py`.

### 1. Persiapan VPS
Buka terminal SSH Anda dan sambungkan ke VPS (misal: `ssh root@ip_vps_anda`).
Update sistem VPS Anda terlebih dahulu:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv git tmux -y
```

### 2. Pindahkan File Bot ke VPS
Gunakan klien SFTP (seperti FileZilla, Cyberduck, atau WinSCP) untuk mengunggah folder `hedge` (beserta isinya) dari komputer lokal ke dalam VPS Linux Anda. 
Letakkan di direktori yang mudah dijangkau, misalnya `/root/hedge`.

### 3. Instalasi Requirements (Virtual Environment)
Sangat disarankan membuat *Virtual Environment* di VPS agar instalasi bot bersih dan tidak merusak library bawaan Ubuntu.

Masuk ke folder bot:
```bash
cd /root/hedge
```
Buat dan aktifkan *Virtual Environment*:
```bash
python3 -m venv venv
source venv/bin/activate
```
Instal semua modul yang dibutuhkan menggunakan `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 4. Konfigurasi Kredensial (.env)
Pastikan file `.env` sudah ada di dalam folder `/root/hedge` di VPS Anda. File ini **SANGAT RAHASIA** dan memuat Private Key Anda.
Jika perlu dibuat dari nol di VPS, ketik:
```bash
nano .env
```
Isi format `.env` riil Anda:
```env
POLYMARKET_PRIVATE_KEY=private_key_anda
POLY_API_KEY=api_key_anda
POLY_API_SECRET=api_secret_anda
POLY_API_PASSPHRASE=api_passphrase_anda

POLY_WS_URL=wss://ws-subscriptions-clob.polymarket.com/ws/market
CLOB_HOST=https://clob.polymarket.com

PAPER_TRADING_MODE=False
TARGET_MAX_ODDS=0.40
MAX_TOTAL_HEDGE_COST=0.85
ABSOLUTE_SLIPPAGE=0.04

GOLDEN_WINDOW_START_SEC=300
GOLDEN_WINDOW_END_SEC=20

BASE_TRADE_USD=2.0
MAX_POSITION_USD=2.5
```
*(Tekan `Ctrl+X`, `Y`, `Enter` untuk menyimpan).*

### 5. Cara Menjalankan Bot di Background (menggunakan Tmux)
Karena ini VPS (jendela terminal akan mati saat Anda memutuskan SSH), Anda membutuhkan `tmux` agar bot (dan UI-nya) terus berjalan (24/7).

Buat sesi terminal virtual bernama "sniper":
```bash
tmux new -s sniper
```
Di dalam layar `tmux` tersebut, aktifkan ulang *virtual environment* lalu jalankan bot:
```bash
source venv/bin/activate
python main.py
```
Dashboard *Rich UI* Anda akan muncul dan bot kini aktif mengeksekusi secara otonom!

### Cara Keluar dan Masuk VPS Tanpa Mematikan Bot
- **Untuk Keluar/Tinggalkan Layar (Detach):** Tekan `Ctrl+B`, lepaskan, lalu tekan `D`. Anda akan dikembalikan ke terminal utama dan bisa menutup jendela SSH. Bot **TETAP BERJALAN** di *background*.
- **Untuk Melihat Bot Lagi (Attach):** Kapan pun Anda login SSH lagi ke VPS dan ingin melihat performa UI bot, cukup ketik:
  ```bash
  tmux attach -t sniper
  ```
  
> **DISCLAIMER:** Pastikan untuk secara rutin memantau `EXECUTIONS` log pada UI untuk memeriksa *slippage* dari API yang mungkin berfluktuasi tergantung dari kepadatan RPC server yang digunakan ClobClient.
