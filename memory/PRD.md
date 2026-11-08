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

## Pending / needs user
- Keys: MIDTRANS_SERVER_KEY, XENDIT_SECRET_KEY, XENDIT_WEBHOOK_TOKEN, FONNTE_TOKEN (payments return 503 & WhatsApp skipped until set)
- Set webhook URLs in Midtrans/Xendit dashboards to {backend}/api/payments/...

## Backlog
- P1: shipping cost by city/courier, stock sync with website, push product edits from admin
- P2: vouchers, reviews, reorder button
