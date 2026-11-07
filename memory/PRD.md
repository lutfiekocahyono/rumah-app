# Pusat Grosir Sidoarjo - E-commerce Mobile App

## Original Problem
"Bangun aplikasi mobile: seperti ruparupa.com yang siap install di android dan ios". Store name: Pusat Grosir Sidoarjo.
User choices: all MVP features, email+password + guest auth (Google requested, deferred), mock checkout, dummy seed data, ruparupa orange style.

## Architecture
- Expo Router (SDK 58) frontend, 4 tabs: Home, Kategori, Keranjang, Akun; stack screens: product/[id], category/[id], search, checkout, order-success, wishlist, orders, login, register
- FastAPI + MongoDB backend (/api): auth (JWT), categories, products (filter/search/sort), cart, wishlist, checkout (mock), orders
- Guest identity via X-Guest-Id header; guest cart/wishlist merged into account on login/register

## Implemented (2026-06)
- Home banner carousel, categories, recommended grid
- Category sidebar + category page with sort chips, search
- Product detail with gallery, qty, add to cart / buy now, wishlist
- Cart with qty stepper, checkout form + mock payment, order success, order history
- Email/password login/register, guest mode, logout
- 8 categories / 21 seeded products; demo user demo@pgs.id / Demo1234!

## Backlog
- P0: Google sign-in (Emergent managed)
- P1: Real payment (Midtrans/Xendit), saved addresses, admin product management
- P2: Product reviews, vouchers/promo codes, share product link
