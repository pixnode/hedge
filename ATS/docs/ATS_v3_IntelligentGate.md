# ATS v3.0: Intelligent Gate + Adaptive Executor

**Two-System Architecture: Model as Gate · ATS as Executor · Pool Memory as Brain**

---

## 📊 Backtest Baseline (1,000 Windows)

| Metric | Value | Assessment |
| :--- | :--- | :--- |
| **Total Windows** | 1,000 | Baseline dataset |
| **HEDGED** | 26 (2.6%) | Terlalu selektif |
| **PANIC EXIT** | 3 (0.3%) | Controlled |
| **SKIPPED** | 971 (97.1%) | Skip rate kritis |
| **Net PnL** | $6.96 | Avg $0.283/hedge |
| **Avg Combined** | 0.858 | Di atas 0.80 threshold! |

> [!IMPORTANT]
> **CRITICAL INSIGHT:** Skip rate 97.1% dan avg combined 0.858 mengindikasikan constraint belum diterapkan dengan benar di backtest ini. Sistem Intelligent Gate dirancang untuk menyelesaikan masalah ini sekaligus meningkatkan kualitas entries yang masuk.

---

## 1. Visi Arsitektur: Bot yang Berevolusi
ATS v3.0 bukan lagi sekadar arbitrage executor. Ini adalah sistem dua lapis yang memisahkan tanggung jawab secara bersih — satu sistem berpikir, satu sistem bertindak — dengan memori yang terus belajar dari setiap keputusan.

**Filosofi inti:** Arbitrage edge dipertahankan sepenuhnya. Intelligence ditambahkan sebagai filter dan optimizer, bukan sebagai pengganti. Bot berevolusi menjadi lebih pintar melalui Pool Memory — bukan melalui perubahan strategi inti.

### 1.1 Tiga Evolusi dari v1 ke v3

| Aspek | ATS v1.0 | ATS v2.0 | ATS v3.0 |
| :--- | :--- | :--- | :--- |
| **Decision** | Rule-based | State machine ketat | Model-gated + adaptive |
| **Intelligence** | Tidak ada | Tidak ada | LightGBM + Convergence |
| **Memory** | Tidak ada | Tidak ada | Pool Memory SQLite |
| **Skip logic** | Harga saja | Harga + timing | Harga + timing + confidence |
| **Learning** | Tidak ada | Tidak ada | Weekly retrain otomatis |
| **Smart Money** | Tidak ada | Tidak ada | Convergence Signals |

---

## 2. Two-System Architecture
Prinsip *separation of concerns* yang paling ketat: Model tidak boleh tahu cara eksekusi, ATS tidak boleh tahu cara berprediksi. Keduanya berkomunikasi melalui satu interface yang bersih.

### 2.1 Interface Contract
Interface adalah satu-satunya titik komunikasi antara kedua sistem. Model menulis, ATS membaca.

| Field | Type | Deskripsi |
| :--- | :--- | :--- |
| `window_id` | str | Identifier unik window (e.g. BTC5M_20260428_1430) |
| `signal` | enum | BULL / BEAR / NEUTRAL — output utama model |
| `confidence` | float 0–1 | Tingkat keyakinan model terhadap signal |
| `p_up` | float 0–1 | Probabilitas BTC naik di window ini |
| `p_down` | float 0–1 | Probabilitas BTC turun di window ini |
| `convergence_score` | float 0–1 | Smart money convergence strength (0=diverge, 1=strong agree) |
| `news_impact` | float -1 to 1 | Sentiment berita (-1=sangat negatif, +1=sangat positif) |
| `dynamic_target_adj` | float | Penyesuaian target entry yang direkomendasikan model |
| `gate_decision` | enum | ENTER / SKIP / WAIT — keputusan final gate |
| `generated_at` | timestamp | Waktu signal dibuat (untuk latency monitoring) |

### 2.2 Sistem A: Intelligent Gate (Model)
Sistem A berjalan async, paralel, jauh sebelum window dimulai. Outputnya sudah tersedia sebelum T-15.

| Komponen | Input | Output |
| :--- | :--- | :--- |
| **Feature Builder** | Binance WS: aggTrade, depth, kline | 12 features (CVD, OB Imbalance, etc) |
| **LightGBM** | 12 features snapshot | `P_UP_raw` |
| **Platt Scaling** | `P_UP_raw` | `P_UP_cal` (Calibrated) |
| **Convergence Engine** | Funding rate, OI, large flow | `convergence_score` 0–1 |
| **News Agent** | CryptoPanic API | `news_impact` -1 to +1 |
| **Ensemble** | Combined signals | `Final_P`, Confidence, `gate_decision` |

### 2.3 Sistem B: ATS Executor
Sistem B hanya membaca `gate_decision` dari Interface Contract. Tidak ada logic model di dalam ATS.

| gate_decision | ATS Action | Catatan |
| :--- | :--- | :--- |
| **ENTER** | Jalankan Pillar 1 sniper normal | `dynamic_target_adj` diterapkan |
| **SKIP** | Skip window sepenuhnya | Log reason ke Pool Memory |
| **WAIT** | Monitor tapi tidak eksekusi | Evaluasi ulang |

---

## 3. Intelligent Gate — Detail per Komponen

### 3.1 Confidence Gate: Worth Entering?
Prinsip: Model skip bukan karena arah salah, tapi karena kondisi tidak ideal. Setiap skip yang tepat adalah uang yang tidak hilang.

| Kondisi Skip | Threshold | Alasan |
| :--- | :--- | :--- |
| **Confidence < threshold** | < 0.55 | Model tidak yakin — probabilitas adverse fill tinggi |
| **High-impact econ event** | Kalender | Fed rate, CPI — volatilitas tidak terstruktur |
| **Convergence negatif** | score < 0.3 | Smart money diverge — sinyal konflik berbahaya |
| **News impact ekstrem** | < -0.7 | Sentiment ekstrem menciptakan satu arah dominan |
| **Dead zone aktif** | Config | Jam low-liquidity — slippage tidak terkontrol |

---

## 4. Pool Memory — Otak yang Berkembang
Implementasi: SQLite lokal (zero dependency).

### 4.1 Schema Pool Memory
- `window_id`: Identifier unik.
- `ats_status`: HEDGED / PANIC / SKIPPED.
- `ats_pnl`: Actual PnL.
- `model_correct`: Apakah signal model terbukti benar.
- `features_snapshot`: JSON snapshot 12 features untuk retrain.

---

## 5. Roadmap Evolusi
1.  **Phase 1 — Foundation:** Gate sebagai filter aturan. Pool Memory mulai mencatat.
2.  **Phase 2 — Learning:** Automated weekly retrain. Confidence threshold adaptif.
3.  **Phase 3 — Adaptive:** Dynamic target adjustment menjadi learned.
4.  **Phase 4 — Beyond Arbitrage:** Directional trades ketika confidence > 0.85.
