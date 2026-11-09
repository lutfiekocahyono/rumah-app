# Pusat Grosir Sidoarjo - E-commerce Mobile App (iOS, Android, Web)

## Original Problem
"Bangun aplikasi mobile: seperti ruparupa.com yang siap install di android dan ios". Store: Pusat Grosir Sidoarjo (PGS).
Iteration 2: import all data from pusatgrosirsidoarjo.com; tiered pricing (pembeli langsung / pengecer / reseller + qty) set manually in admin; Google login; Midtrans + Xendit payments; mobile-first admin panel on web/iOS/Android; WhatsApp order notification to owner (+62 813-3555-1252); "Pesan via WhatsApp"; PGS logo; orange theme; owner tests on iPhone.

## Architecture
- Expo Router SDK 58: tabs (Home, Kategori, Keranjang, Akun) + stacks: product/[id], category/[id], search, checkout, order/[id], orders, wishlist, store, login, register, admin/{index, orders, order/[id], pricing, customers, products, product/[id]}
- FastAPI + MongoDB. Modules: server.py (routes), pricing.py (tier engine), payments.py (Midtrans Snap / Xendit Invoice), notify.py (Fonnte WhatsApp), import_pgs.py (WooCommerce Store API importer, idempotent)
- Auth: JWT (email/password), Emergent Google → /api/auth/session, guest via X-Guest-Id (merged on login). Roles: admin/customer; customer_type set by admin only.
- Pricing: unit price = per-product manual tier for the customer type if set, else website price × (1 − type%) × (1 − qty tier%).

## Implemented
- 2026-06 (iter 1): MVP shop, cart, mock checkout, wishlist, search, email auth, guest
- 2026-06 (iter 2): 6,618 products + 80 categories + 3 branches/contacts imported; tiered pricing engine + UI (tier table, next-tier hint, savings); admin panel (dashboard, orders + status, pricing, customer types, per-product tiers); Google login; Midtrans/Xendit/COD checkout + order status refresh + webhooks (/api/payments/midtrans/notification, /api/payments/xendit/callback); Fonnte WhatsApp notify; Pesan via WhatsApp; PGS logo/icon/splash; stock decrement
- 2026-06 (iter 3): price range (termurah - termahal across all customer types & qty tiers) under price on product cards; full price table (rows = jumlah beli, columns = Pembeli Langsung/Pengecer/Reseller, highlights user's column & active row) on product detail. API adds price_min, price_max, price_matrix.
- 2026-06 (iter 4): reusable one-tap Google button (src/components/google-button.tsx) on Login, Register ("Daftar dengan Google") and Akun guest card; new Google users auto-registered as Pembeli Langsung.
- 2026-06 (iter 5): admin Pengaturan Harga supports % or Rupiah per pcs (toggle) for customer-type discounts and qty tiers (pricing.type_discount_modes, qty_tiers[{min_qty, mode, value}]); legacy discount_percent still read.
- 2026-06 (iter 6): product card restyled like website: bold name, "✓ N stok tersedia", one-line blue price range (theme token priceLink) or single price when no range.
- 2026-06 (iter 7): "Hemat Rp…/pcs" green label on product card image when wholesale tiers apply for the customer; product detail "Harga Grosir" table like website (QUANTITY | DISCOUNT (%) | HARGA, active row solid blue, tap row sets qty); detail price in blue.

## Pending / needs user
- Keys: MIDTRANS_SERVER_KEY, XENDIT_SECRET_KEY, XENDIT_WEBHOOK_TOKEN, FONNTE_TOKEN (payments return 503 & WhatsApp skipped until set)
- Set webhook URLs in Midtrans/Xendit dashboards to {backend}/api/payments/...

## Backlog
- P1: shipping cost by city/courier, stock sync with website, push product edits from admin
- P2: vouchers, reviews, reorder button

## Iteration 3 — Homepage promo features (DONE, tested)
- Home order: Search → Banner promosi (admin-managed, upload via Emergent Object Storage) → Kategori → Gratis Ongkir info banner → Flash Sale (countdown) → Voucher (klaim) → Produk Populer → Produk Terbaru → Rekomendasi (load more).
- Flash sale: admin picks products, flash price, end time; flash price applied in product detail + cart (min of tier price & flash price). Settings key `flash_sale`.
- Vouchers: collection `vouchers` (percent/rupiah, max_discount, min_purchase, quota, ends_at, active, show_on_home); claim (`voucher_claims`), apply at checkout, used count increments; released on cancel/expired/failed. Midtrans/Xendit get negative voucher line.
- Gratis ongkir: info only (settings key `home.free_shipping`); shipping still Rp25.000.
- Rekomendasi: `home.recommend_mode` personal (activity: viewed + purchased categories) | random.
- Admin screens: /admin/banners, /admin/flash-sale, /admin/vouchers, /admin/home-settings.
- Backlog: per-user voucher limit (not requested yet), delete confirmations in admin.

## Iteration 4 — Akun pengguna + dasar toko penjual (Phase 1 of marketplace)
- Akun: register (min 8), login/logout (confirm), Google, verifikasi email (kode 6 angka via Emergent email), OTP HP via WhatsApp Fonnte (OTP_TEST_MODE=true → kode tampil di layar), lupa password, ubah/buat password (revokes old sessions), edit profil, foto profil (object storage), multi alamat (checkout picker), wishlist, riwayat aktivitas (activity_logs + recently viewed), pengaturan notifikasi, kotak notifikasi (order/promo/security).
- Rate limits: login fail 10/15min per email, code requests/confirm limited (rate_limits TTL).
- Seller: anyone opens store → pending → admin verifies (/admin/stores). Existing 6,618 products = store "PGS Official". Seller CRUD products with photos (/seller, /seller/product/[id]); public store page /shop/[id]. Seller products have flat price (no PGS tier pricing).
- Confirm dialogs on delete banner/voucher/address/product + logout.
- Backend modules: account.py, seller.py, mailer.py (registered from server.py).
- NEXT Phase 2: multi-store transaksi (split order per toko, ekspedisi/ongkir RajaOngkir, resi, konfirmasi terima, komisi, saldo, penarikan), chat, review. Phase 3: super admin dashboard (users, komisi, refund, komplain, roles, laporan).

## Iteration 5 — 3 toko resmi + transaksi per toko (DONE)
- Official stores: PGS Sidoarjo (store_id pgs-official, renamed from PGS Official, owns shared catalog), Mitra PGS Jombang (pgs-jombang), Mitra PGS Jember (pgs-jember). Each has own store_admin account (see test_credentials).
- Shared catalog; branch stock in `store_stock` (Jombang/Jember seeded with copy of Sidoarjo stock as sample). Buyer picks store once (/pilih-toko, AsyncStorage, header X-Store-Id). Branch own products visible only in that branch.
- Cart items carry store_id; cart page groups by store; checkout per store with courier (manual tariffs per store: Ambil di toko, JNE, J&T, SiCepat; edit via /seller/couriers or admin /admin/store-couriers/[id]).
- Order: store_id/name, courier, tracking_number, status_history. Store admin: /seller/orders → process → ship (resi required unless pickup) → buyer "Pesanan Sudah Diterima" → completed. Cancel restores stock + voucher.
- No commission: revenue report /seller/report and /admin/report (per store).
- Backlog: super admin dashboard (users, refunds, complaints, roles), chat, reviews, RajaOngkir optional, admin acting as any store.

## Iteration 6 — Ongkir otomatis RajaOngkir (Komerce)
- backend/shipping.py: owner enters API key at /admin/shipping (encrypted with KEY_ENCRYPTION_SECRET, never returned), default weight per item, origin kecamatan per store. JNE/J&T/SiCepat cost via rajaongkir.komerce.id (cheapest service, 30-min cache); fallback to manual tariffs when no key/origin/destination or API error. Pickup & custom couriers stay manual.
- Checkout: buyer searches destination kecamatan when auto is on; POST /api/shipping/rates; checkout recomputes cost server-side.
- Admin panel guarded client-side (app/admin/_layout.tsx) for role admin only; store admins only see their store.

## Iteration 7 — Komplain & Refund + Saldo + Chat Pembeli–Toko (DONE, tested iteration_7)
- backend/support.py. Komplain: buyer files from order detail after shipped/completed, max 7 days, 1 per order, text only, optional refund amount. Branch store owner decides while open (refund/reject with reason/resolve); buyer may escalate a rejection once → Super Admin decides; super admin sees all at /complaint?scope=admin and can decide open ones too.
- Refund → Saldo (wallets, wallet_tx). /wallet screen. Checkout "Pakai saldo" (use_balance; full coverage = payment_method saldo, status paid). Saldo returned once on cancel/expired/failed (minus already refunded). Midtrans/Xendit get negative "Potongan Saldo" line.
- Chat: conversation per buyer+store (buyer must have ordered there); store opens from seller order detail. Polling 4s, unread counters, inbox notification on first unread. Screens /chat, /chat?side=store, /chat/[id].
- Backlog: unread badge on menu, photo evidence (user chose text only for now).
- Iteration 7b: unread chat badges (src/components/unread-badge.tsx) on Akun menu 'Chat Toko' (buyer) & 'Kelola Toko' (store), and seller dashboard Chat tile. DONE
- Iteration 7c: refund only for paid amount — COD counts as paid only when order completed; unpaid COD refundable = saldo portion only (support.paid_amount). UI hides 'Setujui refund' + shows warning. DONE
- Iteration 8 (tests): chat/badges/complaint/COD-refund + real RajaOngkir rates for 3 stores verified. Open minor items: checkout fallback silently uses manual rate if API fails, guest quota/rate-limit on search, ETA 'day'->'hari', status shows auto with invalid key, admin any-status transitions, checkout UX (courier stays pickup after destination, default Midtrans, Kota not auto-filled).
- Iteration 9: checkout auto-picks cheapest courier after destination, Kota auto-filled from destination label, COD default & first, ETA normalized to 'N hari' (shipping._eta_id), name prefill after auth load, stale rate responses ignored. Tested iteration_9.
- Iteration 10: checkout sends expected_shipping_cost; server returns 409 if fresh quote differs or courier gone; frontend shows message and reloads rates (ratesKey), keeps buyer's courier on reload.
- Iteration 11: addresses store destination_id/destination_label (area ongkir) — form search autofills city/postal; checkout uses saved area instantly; area found at checkout is saved back to the address (with city/postal). Tested iteration_11.
- Iteration 12: RajaOngkir key check — key_status {valid|invalid|limited|unknown} via POST /admin/shipping/verify-key, auto-check on save, set on live errors; buyer quotes/search/status skip invalid/limited key (manual tariff) and auto re-check every 30 min. Admin UI status card + 'Cek Kunci Sekarang'.
- Iteration 13: Midtrans keys via Admin > Pengaturan Pembayaran (/admin/payments): server key encrypted in db.settings payment_midtrans, sandbox/production mode, verify via Midtrans status API (404=valid,401=invalid), GET /api/payments/methods drives checkout (Midtrans hidden until valid key); COD default. Notification URL shown for Midtrans dashboard.
- Iteration 14 (ruparupa-style branches): backend/branches.py — POST /api/stores/suggest {area, product_ids, quantities} (distance via static East Java coords from area label/city, suggested = nearest with all stock), GET /api/products/{id}/availability?area=, POST /api/cart/move {from_store_id,to_store_id}. Stores have address & pickup_hours (seller form). UI: product page 'Ketersediaan di toko' (pd-branch-stock), pilih-toko distances + Terdekat badge, checkout BranchSwitcher (pickup box with other branches; nearest banner co-nearest-banner).
- Iteration 15: COD only for pickup (server 400 otherwise; delivery requires Midtrans/Xendit or full saldo). COD pickup orders get expires_at=+48h; background loop (5 min, server._expire_loop) auto-cancels status 'cod' past expires_at with restock/voucher/saldo return + notification. Seller: POST /seller/orders/{id}/extend {hours}, POST /seller/orders/{id}/ready (pickup+processing) sets ready_at + notifies buyer. UI: seller order extend 24/48h + 'Siap Diambil'; buyer order pickup card; checkout hides COD for delivery.
- Iteration 16: pickup_code (6 digits) on pickup orders shown to buyer (order-pickup-code) and seller (so-pickup-code); pickup orders hide resi/address; checkout hides address/city/destination for pickup (backend requires address only for courier); store phone/address/pickup_hours optional.
- Iteration 17: remind_expiring_cod() in _expire_loop notifies store owner once when COD pickup order is within 6h (COD_REMIND_HOURS) of auto-cancel; flag expiry_reminded reset on extend. Verified via API.
- Iteration 18: listings (/products without ?store, /recommendations) use ALL_BRANCHES ctx: all branches' products visible, shared catalog stock summed, store_name 'PGS · semua cabang'. Product detail & add-to-cart lookup across all branches; stock/cart still per selected store. Home label 'Produk semua cabang · toko pilihan'.

## Refactor (Iteration 18)
- backend/server.py split: marketing.py (banners, vouchers, flash sale, home settings, uploads/files) and order_tasks.py (release voucher/stock/saldo, COD 48h auto-cancel + reminder loop). Routes unchanged (138).
- frontend/app/checkout.tsx split into src/components/checkout/ (styles, fields, voucher-section, payment-section, courier-list). testIDs unchanged.
- Backlog: retire/update old test suites (iter2, iter4-14) written for previous rules.

## Iteration 19
- GET /api/products/count; home & admin search placeholder use real count.
- Free-shipping subtitle supports {kota} placeholder → city of the chosen branch (old "Area Sidoarjo" text auto-converted).
- Seller order list: COD pickup orders show auto-cancel chip; red border + red chip when ≤6h left (timezone-safe parse via parseDate).

## Iteration 20
- "Pesanan siap diambil" notification now includes pickup code and COD cash amount due.

## Iteration 20 — Produk di Beranda (per cabang)
- backend/home_feed.py: GET /api/home/sections, /api/home/sections/recommended; GET/PUT /api/seller/home-sections (official branch admins), /api/admin/home-sections/{store_id}.
- Per section: show/hide, title, limit, sort (terlaris/rating/paling dilihat/terbaru-restok/acak/+sesuai minat for rekomendasi), category filter, manual pins (ordered, merged across branches, buyer's branch first), Terbaru window N days (upload OR restock).
- products.sold += on completion (once), -= on later cancel; products.views on view; products.restocked_at when stock raised.
- Screens: /seller/home-sections (Beranda nav, official branches), /admin/home-sections (branch chips).

## Iteration 21
- POST /api/admin/home-sections/{id}/copy-pins (super admin): copies manual picks of all 3 sections to other branches (only pinned fields). UI: hs-copy button + confirm on /admin/home-sections.

## Iteration 22
- Wholesale display unchanged; pricing settings had been wiped by legacy test teardown. Tests now snapshot/restore pricing. User re-enters values in Admin → Pengaturan Harga.

## Iteration 23 — Seller Center: Tambah Produk (Tahap 1)
- backend/product_editor.py: /api/product-editor/{context,upload,drafts,drafts/{id},products/{id},publish}. Admin -> any active store; seller/branch admin -> own store.
- Product fields: brand, sku, condition, showcase, status (inactive hidden via _visible), video, min/max order, low_stock_alert, variant_options, variants[{variant_id,values,name,price,stock,sku,image,active}].
- Cart lines keyed `product_id::variant_id`; PUT/DELETE /api/cart/items/{key}; checkout enforces min/max order; variant stock adjusted via arrayFilters; variant products keep own stock (no branch store_stock).
- Frontend: /product-editor/[id] (new|product_id, ?draft=), SellerShell sidebar (≥900px fixed, else drawer), sections Informasi Dasar (rich editor), Foto & Video (multi, drag&drop web, reorder, main, replace, progress), Variasi (table), Harga & Stok, kelengkapan; Simpan Draft + Publikasikan with confirm. Product detail variant picker + RichText.
- Phase 2 pending: sections 7,8,9, other buttons (Preview, Simpan & Tambah Baru, Batalkan), 12 (autosave, duplicate, import/export, bulk edit, history).

## Iteration 24 — Tahap 2 Spesifikasi & Pengiriman
- ProductForm: specs{material,color,size,dimensions,weight,origin_country,warranty,extra}, weight_grams (required), L/W/H cm, couriers (empty=all), ship_regular, ship_cargo, preorder(+days 1-90), processing_days.
- shipping.quote(store, dest, items): billable weight = max(actual, LxWxH/6000 kg) per item; product courier limits intersect; cargo couriers (name/code cargo|kargo|trucking|jtr) only if all products allow cargo.
- /product-editor/context returns shipping{store:{origin,pickup,couriers[cargo flag]}}.
- Product page: Spesifikasi table + pre-order/processing info.

## Iteration 25 — SEO & Tombol
- ProductForm: seo_title(<=70), meta_description(<=160), keywords(<=10). SeoSection: title ideas, meta auto, keyword ideas, SERP preview, score 0-100 checklist.
- Buttons: Batalkan (confirm if unsaved), Preview Produk (modal from unsaved form), Simpan & Tambah Baru (publish then fresh form keeping category/etalase), Simpan Draft, Publikasikan.

## Iteration 27 — Tahap 3
- Daftar Produk (/product-editor/list): cari, filter, pilih banyak, Edit Massal harga/stok/status, Duplikat, Ekspor/Impor Excel (template, preview sebelum terapkan, baris belum lengkap -> draft).
- Editor: simpan otomatis draft 4 detik setelah perubahan, tombol Duplikat, banner lanjutkan draft autosave untuk produk yang diedit.
- Iter 28: impor menerima .csv/.xlsx ekspor website (WooCommerce), pencocokan kolom tampil sebelum simpan, template berisi 2 contoh produk asli + sheet Petunjuk Kolom, kolom Link Website di ekspor.
- Iter 29: Riwayat Harga & Stok (/product-editor/history), Super Admin semua toko, admin cabang hanya tokonya.
- Iter 30: Harga grosir Rupiah per tingkat per produk di Tambah/Ubah Produk; Pengaturan Harga global dihapus setelah potongan lama disalin ke semua produk.
- Iter 31: Ekspor riwayat Excel per toko & periode; menu bar bawah global (Beranda, Kategori, Scan, Keranjang, Akun) + pencarian atas di semua halaman kecuali login & checkout; Scan barcode produk & kode ambil pesanan; field Barcode di editor.
- Iter 32: Fix QR link 404; Accurate Online Tahap 1 (kunci API terenkripsi, uji koneksi, gudang, pratinjau barang baca-saja).
- Iter 34: QR kode ambil di halaman pesanan pembeli (PGSAMBIL-<kode>), dikenali Scan kasir dari mode mana pun.
- Iter 35: Panduan daftar aplikasi Accurate (salin App URL/Callback), tombol Chat di detail produk (cabang terpilih), teks COD pesanan selesai diperbaiki.
- Iter 35b: chat dari halaman produk diizinkan sebelum memesan (product_id), overflow salin callback diperbaiki.

## Iteration 36 (Jun 2026)
- Chat dari detail produk otomatis mengirim kartu produk (nama lengkap, foto, harga, SKU) sekali per produk.
- Accurate Tahap 2A: tarik harga (katalog bersama), stok per cabang (gudang terpetakan), barang baru (nonaktif) dengan pratinjau + centang per baris, konflik dilewati, tercatat di Riwayat (sumber "Sinkron Accurate"). Accurate tidak diubah.
- Accurate Tahap 2B: faktur penjualan per pesanan (lunas / COD selesai) setelah konfirmasi; nomor faktur = nomor pesanan; kode pelanggan & kode barang ongkir di pengaturan.
- Belum diuji dengan akun Accurate asli (memakai mock tests/accurate_mock.py).

## Iteration 37 (Jun 2026)
- Balasan Cepat Toko: template per cabang (5 bawaan: stok tersedia/habis, harga grosir, jam ambil, ongkir), bisa ditambah/ubah/hapus admin cabang; kata otomatis {produk} {harga} {pembeli} {toko}. Chip tampil di chat sisi toko, ketuk = isi kolom pesan.
- Pesan sukses kirim faktur Accurate kini tetap tampil sampai ditutup.

## Iteration 38 (Jun 2026)
- Notifikasi info produk ke SEMUA pembeli (lonceng + email terverifikasi): produk baru, harga, stok/tersedia lagi, keterangan/foto/info lain. Digabung jadi 1 ringkasan per pembeli maks 1x per jam (product_notify.py). Halaman /product-updates/[id]. Pembeli bisa mematikan di Akun → Pengaturan (Info produk / Email info produk). Admin: POST /api/admin/product-digest/run untuk kirim sekarang.
- Penjualan (stok berkurang karena pesanan) tidak memicu notifikasi; produk yang disembunyikan tidak diumumkan.

## Iteration 39 (Jun 2026)
- Filter pencarian: urutan (Terbaru, Terlaris, Harga termurah/termahal), rentang harga min/maks, merek (multi, cari), kategori (dengan semua sub-level; "Lainnya" untuk produk tanpa kategori), tersedia di cabang pilihan, ada harga grosir. GET /api/products/facets.
- Merek: diimpor dari atribut Brand website (import_brands.py, 4607/6618 produk). Input Merek di editor dengan saran merek yang ada; server menyamakan ejaan merek yang sudah ada.

## Iteration 40 (Jun 2026)
- Fondasi push HP (Emergent managed push / SuprSend): backend push.py (/api/push/config, /api/register-push [auth, own user only], /api/admin/push GET/PUT), default NONAKTIF; ringkasan info produk per jam ikut dikirim sebagai push bila aktif (chunk 100). Frontend: expo-notifications + expo-device, handler & channel di _layout, PushManager (tap routing, daftar token hanya jika push aktif, ajakan buka Pengaturan mingguan), halaman Admin → Notifikasi Push HP.
- Belum: google-services.json (pemilik belum punya Firebase) → android.googleServicesFile sengaja belum dipasang agar build tidak gagal. EMERGENT_PUSH_KEY=placeholder diisi otomatis saat deploy.

## Iteration 41 (Jun 2026)
- Berat produk: semua 6.618 produk impor belum punya berat. Daftar Produk menampilkan jumlah "belum ada berat" / "berat perkiraan", filter keduanya, badge per baris, Edit Massal "Isi Berat" (hanya yang kosong / timpa), Excel (kolom Berat (gram)).
- Perkiraan otomatis (weight_estimate.py): aturan nama (AC, TV per ukuran, kulkas, dispenser, speaker, kipas, lemari, dll.) lalu kategori; ×N untuk per dus/isi N; pratinjau dengan edit/buang per baris, konfirmasi, lalu disimpan dengan tanda weight_estimated sampai dikoreksi (editor/massal/Excel).
- Perubahan berat tidak memicu notifikasi pembeli; perbaikan on_info agar field default produk impor tidak dianggap berubah.

## Iteration 42 (Jun 2026)
- Halaman pencarian = "Katalog Produk": default semua produk urut Terbaru; tab bawah "Katalog" (/katalog) menggantikan Kategori; kotak cari membuka /search?focus=1. Filter kategori tetap di lembar Filter.
- Notifikasi: perubahan berat saja (editor/Excel) tidak lagi memicu "info diperbarui" (abaikan pergantian thumbnail & pemecahan kategori impor).
- Catatan: 220 produk impor berkategori "lainnya" (tidak ada di daftar kategori) — editor minta pilih kategori dulu; Excel tetap bisa.

## Iteration 43 (Jun 2026)
- Ukuran dus (P×L×T cm): Edit Massal "Ukuran Dus" (hanya yang kosong / timpa), Excel (kolom Panjang/Lebar/Tinggi), filter "Belum ada ukuran dus" / "Ukuran perkiraan", banner jumlah, perkiraan otomatis per jenis produk dengan pratinjau + konfirmasi + tanda dims_estimated. Endpoint umum /api/product-editor/{weight|dims}/summary|preview|{id}/apply.
- Perbaikan aturan perkiraan: "Isi N Pcs" tidak lagi dikali (hanya "per dus/karton/koli/lusin", maks 30 kg & 120 cm per sisi), speaker trolley, dispenser kulkas (jar), tisu. Tanda perkiraan ditentukan server saat simpan di editor.

## Iteration 44 (Jun 2026)
- Rapikan kategori "Lainnya" (220 produk impor): banner di Daftar Produk → dialog usulan kategori per produk (kata kunci + produk mirip), ganti kategori per baris, centang/buang semua, konfirmasi sebelum simpan. Tanpa notifikasi pembeli. category_suggest.py, /api/product-editor/uncategorized/summary|preview|{id}/apply.
- Lokasi pelanggan: izin diminta langsung (expo-location), posisi dikirim selama app terbuka (maks tiap 2 menit / pindah 200 m). Tanpa izin → layar kunci (Izinkan lokasi, petunjuk pengaturan, link masuk admin). Admin, admin cabang & login/daftar/lupa password tidak dikunci. customer_location.py (/api/location, /api/admin/customer-locations).
- Admin → Analisa Pelanggan (/admin/customers-map): statistik, filter waktu, tamu, peta Leaflet/OSM (WebView native, iframe web), daftar.
- Admin → WhatsApp Fonnte (/admin/fonnte): token terenkripsi, nomor pemilik, uji koneksi (/device), uji kirim OTP. Token Admin = OTP asli; tanpa token = mode uji. fonnte.py, dipakai account.py & notify.py.
- Perkiraan ukuran dus: ukuran tertulis di nama (+2 cm, kecuali barang lipat), chest freezer, sofa angin. Input P/L/T Edit Massal muat di HP.
- Kalimat privasi lokasi di Akun.
