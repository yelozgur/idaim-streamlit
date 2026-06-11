# IDAIM Google Sheets Headers

Bu dosyayı kullanarak Google Sheets'te 6 sheet oluştur. **Sıra önemli** (FK referansları için).

Sheets adlarını **birebir aynı** kullan (büyük/küçük harf dahil).

---

## Sheet 1: `cells`

| Kolon | Tip | Açıklama |
|---|---|---|
| `cell_id` | int (PK) | 1-642 arası, birincil anahtar |
| `lon` | float | Boylam |
| `lat` | float | Enlem |
| `district` | text | Keryneia / Nicosia / Famagusta / Larnaca / Limassol / Paphos |
| `culex_proba` | float (0-1) | ML çıktısı (Culex) |
| `aedes_proba` | float (0-1) | ML çıktısı (Aedes) |
| `confidence_tier` | text | high / medium / low / unknown |
| `last_updated` | date (YYYY-MM-DD) | Son ML retrain tarihi |

**İlk satır (header) — kopyala:**
```
cell_id	lon	lat	district	culex_proba	aedes_proba	confidence_tier	last_updated
```

---

## Sheet 2: `sampling_initiation`

| Kolon | Tip | Açıklama |
|---|---|---|
| `init_id` | text (PK) | Auto: `INIT-{trap_id}` |
| `trap_id` | text (UNIQUE) | TRP-001 formatında |
| `cell_id` | int (FK → cells) | Hücre referansı |
| `sampling_start_time` | datetime | Kurulum anı |
| `operator` | text | Ceyda / Marlen / Yesim / Gregoris / Mustafa / Costas / Other |
| `sampling_method` | text | Ovitraps / Larvae Collection / BG Sentinel Trap / EVS Trap / Human Land Catching |
| `site_description` | text | rural/remote etc. |
| `comments` | text | Serbest not |
| `photo_urls` | text (virgülle ayrılmış) | Drive URL listesi |
| `state` | text | active / closed / missing |

**İlk satır:**
```
init_id	trap_id	cell_id	sampling_start_time	operator	sampling_method	site_description	comments	photo_urls	state
```

---

## Sheet 3: `trap_checks`

| Kolon | Tip | Açıklama |
|---|---|---|
| `check_id` | text (PK) | Auto: `CHK-{trap_id}-{seq}` (örn: CHK-TRP-001-1) |
| `trap_id` | text (FK → sampling_initiation) | Hangi trap |
| `check_datetime` | datetime | Kontrol anı |
| `trap_status` | text | Trap Missing / Trap Disturbed / Battery out / Trap valid / Other |
| `comments` | text | Serbest not |
| `image_urls` | text (virgülle ayrılmış) | Drive URL listesi |
| `sampling_finish_id` | text | Auto-computed: `{trap_id}+{start}+{finish}` |

**İlk satır:**
```
check_id	trap_id	check_datetime	trap_status	comments	image_urls	sampling_finish_id
```

---

## Sheet 4: `lab_results`

| Kolon | Tip | Açıklama |
|---|---|---|
| `lab_id` | text (PK) | Auto: `LAB-{trap_id}-{seq}` |
| `trap_id` | text (FK → sampling_initiation) | Hangi trap |
| `sampling_lab_id` | text | Auto-computed: `{trap_id}+{start}+{lab}` |
| `cell_id` | int (FK → cells) | Hücre (ML training için şart) |
| `lab_date` | date | Analiz tarihi |
| `lab_operator` | text | Gregoris / Ceyda / Operator1 / Operator2 / Other |
| `specimen_lifecycle` | text | Egg / Larva / Adult |
| `identification_method` | text | Morphological / Molecular |
| `species` | text | Culex / Aedes / Mixed / Other / Negative |
| `count` | int | Birey sayısı |
| `lab_confidence` | text | high / medium / low (auto-computed) |
| `comments` | text | Serbest not |
| `image_urls` | text | Drive URL listesi |

**İlk satır:**
```
lab_id	trap_id	sampling_lab_id	cell_id	lab_date	lab_operator	specimen_lifecycle	identification_method	species	count	lab_confidence	comments	image_urls
```

**`lab_confidence` otomatik hesaplama (script tarafında):**
- Adult + Molecular = `high`
- Larva + Morphological = `medium`
- Egg + Morphological = `low`
- Diğer kombinasyonlar = `medium`

---

## Sheet 5: `watch_list`

| Kolon | Tip | Açıklama |
|---|---|---|
| `cell_id` | int (PK, FK → cells) | Hücre |
| `species` | text (PK) | culex / aedes (per-species watch list) |
| `proba` | float | ML olasılığı |
| `threshold_used` | float | Per-district veya global threshold |
| `district` | text | District adı |
| `added_at` | datetime | Listeye eklenme zamanı |
| `visited` | bool | Saha gidip trap kurdu mu? |
| `trap_id` | text (FK → sampling_initiation) | Kurulduysa trap_id |

**İlk satır:**
```
cell_id	species	proba	threshold_used	district	added_at	visited	trap_id
```

---

## Sheet 6: `features_cache`

| Kolon | Tip | Açıklama |
|---|---|---|
| `cell_id` | int (PK, FK → cells) | Hücre |
| `feature_year` | int (PK) | 2024 gibi |
| `last_refresh` | date | Son GEE'den çekilme |
| `LST_01` ... `LST_12` | float | 12 ay LST |
| `NDVI_01` ... `NDVI_12` | float | 12 ay NDVI |
| `Humidity_01` ... `Humidity_12` | float | 12 ay humidity |
| `Precip_01` ... `Precip_12` | float | 12 ay precip |
| `WindSpeed_01` ... `WindSpeed_12` | float | 12 ay wind |

**Toplam kolon:** 4 (id) + 60 (feature) = **64 kolon**

**İlk satır:**
```
cell_id	feature_year	last_refresh	LST_01	LST_02	LST_03	LST_04	LST_05	LST_06	LST_07	LST_08	LST_09	LST_10	LST_11	LST_12	NDVI_01	NDVI_02	NDVI_03	NDVI_04	NDVI_05	NDVI_06	NDVI_07	NDVI_08	NDVI_09	NDVI_10	NDVI_11	NDVI_12	Humidity_01	Humidity_02	Humidity_03	Humidity_04	Humidity_05	Humidity_06	Humidity_07	Humidity_08	Humidity_09	Humidity_10	Humidity_11	Humidity_12	Precip_01	Precip_02	Precip_03	Precip_04	Precip_05	Precip_06	Precip_07	Precip_08	Precip_09	Precip_10	Precip_11	Precip_12	WindSpeed_01	WindSpeed_02	WindSpeed_03	WindSpeed_04	WindSpeed_05	WindSpeed_06	WindSpeed_07	WindSpeed_08	WindSpeed_09	WindSpeed_10	WindSpeed_11	WindSpeed_12
```

**Not:** İlk satırı kopyala-yapıştır yaparken **boşluk değil tab** ile ayrılmış olmalı. Yukarıdaki tek satırı direkt Excel/Sheets'e yapıştırabilirsin.

---

## Sheet 7 (opsiyonel): `users`

Basit şifre auth için. POC aşamasında:

| Kolon | Tip | Açıklama |
|---|---|---|
| `username` | text (PK) | Login adı |
| `password_hash` | text | SHA256 hash |
| `role` | text | admin / field / lab / viewer |
| `last_login` | datetime | Son giriş |

**İlk satır:**
```
username	password_hash	role	last_login
```

**Default admin:** `admin` / `idaim2026` (ilk açılışta değiştirilmesi önerilir).

---

## Özet — Sheets Yapısı

```
Spreadsheet: "IDAIM-Cyprus-2026"
├── cells                    (642 satır, 8 kolon)
├── sampling_initiation      (her trap 1 satır)
├── trap_checks              (her trap N satır, N=check sayısı)
├── lab_results              (her trap 1 satır)
├── watch_list               (ML önerileri, dinamik)
├── features_cache           (her hücre 1 satır, 64 kolon)
└── users                    (POC auth)
```

**Toplam: 7 sheet.**

---

## Adım Adım Kurulum

1. Yeni Google Sheets oluştur, adı: `IDAIM-Cyprus-2026`
2. **Sayfa 1** adını `cells` yap, header'ı yapıştır
3. **+** ile yeni sayfa ekle, adını `sampling_initiation` yap, header'ı yapıştır
4. Aynı şekilde diğer 5 sheet'i ekle
5. Spreadsheet URL'inden ID'yi kopyala:
   ```
   https://docs.google.com/spreadsheets/d/{BU_ID}/edit
   ```
6. BU_ID'yi `secrets.toml`'a yapıştır

Sonra `streamlit_app` deploy et (Streamlit Cloud veya lokal).
