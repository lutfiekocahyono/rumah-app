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
