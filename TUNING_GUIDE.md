# Panduan Tuning Parameter ATS v2.0 (`.env`)

Arsitektur ATS v2.0 memperkenalkan serangkaian parameter dinamis yang mengontrol **State Machine 3-Pillar**. Mengubah angka-angka ini secara langsung akan mempengaruhi tingkat agresivitas bot, profil risiko, dan tingkat keberhasilan *fill rate* Anda.

Panduan ini akan menjelaskan cara *tuning* (kalibrasi) setiap variabel yang baru ditambahkan ke dalam file `.env`.

---

## 1. Konfigurasi Sniper Window (Pillar 1)
Pillar 1 adalah fase "pencarian harga diskon" di mana bot mencoba masuk ke market dengan biaya terendah.

*   `P1_SNIPER_OPEN_SEC=10`
    *   **Fungsi:** Detik **sebelum** window baru dimulai di mana bot mulai memonitor orderbook.
    *   **Tuning:** Naikkan ke `15` atau `20` jika bot sering ketinggalan *early dump* dari trader yang panik sebelum window habis. Jangan terlalu tinggi agar bot tidak salah menganalisis token lama.
*   `P1_SNIPER_CLOSE_SEC=10`
    *   **Fungsi:** Detik **setelah** window baru berjalan di mana bot masih menerima posisi baru.
    *   **Tuning:** Naikkan ke `15` jika Anda perhatikan pergerakan awal di 10 detik pertama masih lambat. Turunkan ke `5` jika Anda ingin entry yang sangat ekstrem (tapi *fill rate* akan sangat rendah).

## 2. Agresivitas Execution (Pillar 2)
Pillar 2 aktif jika bot sudah memiliki satu sisi (*exposed position*). Di sini, prioritasnya adalah mendapatkan Leg ke-2, *berapapun harganya* (selama masih profit).

*   `P2_SLIPPAGE=0.13`
    *   **Fungsi:** *Slippage* yang digunakan saat menembak Leg 2.
    *   **Tuning:** Naikkan ke `0.15` atau `0.18` jika market Polymarket sering "loncat" (spread sangat lebar) dan bot sering gagal (*Failed execution*). Turunkan ke `0.11` jika Anda merasa selisih harga terlalu memotong potensi profit, tetapi risiko gagal tereksekusi akan membesar.
*   `P2_PROXIMITY_ALERT=0.05`
    *   **Fungsi:** Jarak antara harga *ask* dengan target dinamis. Jika harga mendekat, bot masuk ke *high-alert loop*.
    *   **Tuning:** Jika Anda mematok nilai `0.05` dan target Anda adalah `0.60`, bot akan mengebut polling saat harga menyentuh `0.65`.
*   `P2_POLL_INTERVAL=0.05`
    *   **Fungsi:** Kecepatan siklus antrean (*queue timeout*) saat dalam kondisi *high-alert*. Semakin kecil, bot semakin cepat merespons (namun CPU lebih berat).

## 3. Rileksasi Target Berbasis Waktu (Target Relaxation)
Bot akan melonggarkan harga target Leg 2 semakin dekat ke waktu kedaluwarsa (T-20). Profit kecil lebih baik daripada *panic sell loss*.

*   `P2_RELAX_LATE=0.02`
    *   **Fungsi:** Tambahan kelonggaran target antara T-LATE hingga T-CRITICAL.
    *   **Tuning:** Contoh: Jika target awal `0.60`, bot kini bersedia membeli di `0.62`. Naikkan menjadi `0.03` jika bot sering diam padahal waktu hampir habis.
*   `P2_RELAX_LATE_SEC=60`
    *   **Fungsi:** Detik keberapa (T-minus) kelonggaran LATE mulai berlaku. Default adalah 60 (mulai saat sisa waktu 1 menit).
    *   **Tuning:** Naikkan ke `80` atau `90` jika Anda ingin *front-running* bot lain dan mengamankan Leg 2 lebih awal.
*   `P2_RELAX_CRITICAL=0.03`
    *   **Fungsi:** Tambahan kelonggaran target mulai fase CRITICAL hingga kedaluwarsa.
    *   **Tuning:** Ini adalah fase terakhir sebelum kepanikan. Target Anda (contoh `0.60`) menjadi `0.63`. Di Overlap Zone (T-25), bot otomatis akan menambah ekstra `0.01` di atas ini.
*   `P2_RELAX_CRITICAL_SEC=40`
    *   **Fungsi:** Detik keberapa (T-minus) kelonggaran CRITICAL mulai berlaku. Default adalah 40.
    *   **Tuning:** Naikkan ke `50` jika Anda ingin mengamankan Leg 2 lebih cepat tanpa menunggu menit-menit paling genting (sebelum T-30).

## 4. Keamanan Overlap Zone & Pillar 3
Pillar 3 adalah *ejector seat* (kursi lontar) bot. Tujuannya hanya satu: menyelamatkan sisa uang dari Leg 1 yang nyangkut.

*   `OVERLAP_ZONE_SEC=25`
    *   **Fungsi:** Titik T-minus di mana bot mempersiapkan limit order untuk Panic Sell.
    *   **Tuning:** Jika API atau node Polygon Anda lambat, naikkan ke `30` agar bot punya ancang-ancang waktu lebih untuk *pre-armed panic sell*.
*   `BID_FLOOR_THRESHOLD=0.05`
    *   **Fungsi:** Batas harga *bid* terendah yang layak di-panic sell. Jika *bid* terlalu murah (< `0.05`), lebih baik posisi dibiarkan hangus.
    *   **Tuning:** Ini adalah fitur pencegah **Liquidity Vacuum**. Turunkan ke `0.03` jika Anda ingin bot *tetap ngeyel* menyelamatkan sisa beberapa sen, walau slippage akan parah. Naikkan ke `0.08` jika memotong kerugian di angka receh tidak setimpal dengan gas/risikonya.

## 5. Prefetch Engine
*   `PREFETCH_SEC=15`
    *   **Fungsi:** Waktu pra-pengambilan (API call) untuk data window selanjutnya sebelum Sniper Window terbuka.
    *   **Tuning:** Default `15` sudah sangat ideal untuk meniadakan *cold-start latency* API Gamma. Jangan terlalu diturunkan ke bawah `10`, dan tidak perlu dinaikkan lebih dari `20` (karena Gamma API kadang belum siap di >20s).

---

## 💡 Strategi Kalibrasi yang Direkomendasikan
Jangan mengubah semua variabel secara bersamaan! Lakukan *A/B Testing* dengan cara:
1. Pastikan `PAPER_TRADING_MODE=True` di `.env`.
2. Ubah satu kategori saja (Misal: hanya ubah `P2_SLIPPAGE`).
3. Jalankan bot (`python main.py`) biarkan berjalan 3–5 siklus window (sekitar 15-25 menit).
4. Analisis di terminal atau pada file `trades.csv` apakah *fill rate* untuk Leg 2 meningkat, dan perhatikan log "PANIC SELL" vs "HEDGED".
5. Jika hasil memuaskan, terapkan ke konfigurasi *Live* Anda.
