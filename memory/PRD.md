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
