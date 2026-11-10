Saya ingin membangun APLIKASI WEB (website, bukan aplikasi mobile) untuk "Pusat Grosir Sidoarjo" (PGS), marketplace grosir peralatan rumah tangga multi-cabang. Website ini menggantikan website lama WooCommerce di domain pusatgrosirsidoarjo.com. Semua tampilan, teks, dan komunikasi memakai Bahasa Indonesia.

## 1. Prinsip utama: pakai server & data yang SUDAH ADA
- Sudah ada aplikasi HP PGS yang live, dengan server FastAPI + MongoDB di: https://rumah-app-1.emergent.host/api
- Website ini WAJIB memakai server dan data tersebut (produk, harga, stok cabang, pengguna, keranjang, pesanan, saldo, chat, komplain). JANGAN membuat database produk/pesanan baru dan JANGAN menyalin data. Website hanyalah tampilan web dari sistem yang sama, jadi data selalu sama dengan aplikasi HP.
- Server sudah mengizinkan akses dari domain lain (CORS terbuka).
- Login memakai token: setelah login, kirim header `Authorization: Bearer <token>` di setiap permintaan.
- Cabang aktif dikirim lewat header `X-Store-Id: <store_id>`. Cabang resmi: `pgs-official` (Sidoarjo, pusat), `pgs-jombang`, `pgs-jember`.
- Halaman toko cabang memakai header tambahan `X-Shop-Page: 1` agar hanya produk yang punya harga di cabang itu yang tampil.
- Kode sumber aplikasi HP (Expo/React Native + FastAPI) akan saya hubungkan dari GitHub sebagai acuan. Pelajari `frontend/src/api.ts` (daftar lengkap ±230 endpoint dan tipe datanya) dan folder `frontend/app/` (semua layar). Ikuti alur, teks, dan aturan bisnis yang sama.
- Jika memungkinkan dan stabil, boleh memakai ulang kode Expo Router itu sebagai versi web (ekspor web) yang diarahkan ke server di atas, agar semua fitur sama persis. Jika tidak, buat ulang tampilannya untuk web dengan alur yang sama.
- Jika ternyata server perlu diubah (misalnya endpoint baru), JANGAN membuat server tiruan. Catat kebutuhannya dan beri tahu saya agar diubah di proyek aplikasi HP.

## 2. Cakupan fase 1: tampilan pelanggan DAN Admin/Seller Center sekaligus

### Pelanggan / tamu
- Beranda: banner, flash sale, bagian beranda yang diatur admin, Merek Unggulan, kategori, Produk Populer, "Rekomendasi untukmu".
- Katalog Produk: pencarian dengan saran, filter (kategori & sub-kategori, merek, rentang harga, "Ada harga grosir", stok), dan urutan.
- Halaman Kategori dan halaman Merek (`/brand/<nama>`) dengan filter dan urutan yang sama.
- Halaman toko cabang (`/shop/<store_id>`): banner, logo, deskripsi, alamat, jam ambil, WhatsApp, tombol "Petunjuk arah ke toko" (Google Maps rute ke pin cabang), kotak "Cari di <nama toko>", kategori, Merek Unggulan cabang, dan produk. Hanya produk yang punya harga di cabang itu yang tampil, termasuk yang stoknya 0.
- Detail produk: foto/video, variasi, harga bertingkat (grosir), stok per cabang ("Ketersediaan di toko"), Produk Serupa, wishlist, bagikan, chat toko.
- Pilih cabang manual, dan cabang terdekat otomatis bila lokasi diizinkan.
- Keranjang, lalu Checkout: alamat pengiriman, kurir (ongkir dari server), ambil di toko, voucher, saldo, dan pembayaran Midtrans.
- Akun: daftar, masuk (email + kata sandi, dan Google), lupa kata sandi, OTP WhatsApp bila diaktifkan, edit profil, ubah kata sandi, pengaturan, riwayat aktivitas, alamat pengiriman (dengan pin peta), saldo saya, notifikasi, daftar & detail pesanan, wishlist, chat toko, komplain (buat, daftar, detail).

### Super Admin (role `admin`) dan admin cabang (role `store_admin`)
Semua halaman Admin Panel dan Seller Center yang ada di aplikasi HP:
- Admin: dasbor, pesanan masuk & detail, kategori pelanggan, tambah/edit/daftar produk (edit massal, duplikat, impor & ekspor Excel, riwayat), Merek & Kategori (logo), Produk Serupa, banner, flash sale, bagian & pengaturan beranda, voucher, pelanggan & peta pelanggan, toko/cabang & kurir toko, salin harga ke cabang, pengiriman, pembayaran, push, laporan, Accurate Online, Fonnte.
- Seller Center (cabang): dasbor, pesanan & detail, harga cabang (impor/ekspor), stok, kurir sendiri, jadwal flash sale, bagian beranda cabang, Tampilan Toko (banner, logo, deskripsi, alamat & kontak, jam ambil, pin lokasi di peta, Merek Unggulan cabang).
- Admin cabang hanya boleh melihat dan mengubah cabangnya sendiri (server sudah menegakkan aturan ini).
- Kotak cari katalog pembeli TIDAK ditampilkan di bagian atas halaman Akun, Admin, dan Seller Center. Kotak cari kerja di dalam halaman (Daftar Produk, Pesanan, Pelanggan, Merek & Kategori, Harga Cabang, Stok) tetap ada.

## 3. Aturan harga & stok cabang (sudah dihitung server, tampilkan apa adanya)
- Satu katalog induk dikelola Super Admin (Sidoarjo). Tiap cabang (Jombang, Jember) punya harga, stok, dan harga grosir bertingkat sendiri (koleksi `store_stock`: store_id, product_id, price, stock, tier_prices).
- Kategori pelanggan: Pembeli Langsung, Pengecer, Reseller. Masing-masing punya harga bertingkat berdasarkan jumlah (maksimal 10 tingkat). Server mengembalikan harga sesuai akun dan cabang aktif.
- Jangan menghitung harga sendiri di web. Selalu pakai angka dari server. Format Rupiah: "Rp157.000".
- Stok, ongkir, dan pilihan "ambil di toko" mengikuti cabang aktif. Keranjang terikat ke satu cabang. Bila pindah cabang, ikuti alur pindah cabang yang ada (endpoint stores/suggest).

## 4. Peta & lokasi
- Peta memakai OpenStreetMap (Leaflet), gratis tanpa kunci.
- Alamat pengiriman BARU wajib punya pin peta (lat/lng). Pembeli bisa ketuk peta, geser pin, cari tempat (tombol "Cari", lewat `/api/geo/search` dan `/api/geo/reverse` yang butuh login), atau "Gunakan lokasi saat ini" lewat izin lokasi browser.
- Admin cabang memasang pin toko di Tampilan Toko. Pin ini dipakai untuk "Petunjuk arah" dan cabang terdekat.
- Lokasi TIDAK wajib. Tampilkan ajakan izin lokasi yang bisa ditutup ("Nanti saja"). Tanpa izin, pembeli memilih cabang manual. Tampilkan pengingat kecil yang bisa membuka ajakan lagi. Admin dan halaman login dikecualikan.

## 5. Pembayaran
- Pakai alur yang sama dengan aplikasi HP: server membuat transaksi Midtrans dan mengembalikan `payment_url`. Web membuka halaman bayar itu, lalu kembali ke halaman detail pesanan dan memperbarui status dari server.
- Jangan menyimpan kunci pembayaran di website. Semua kunci ada di server.

## 6. Batasan web
- TANPA notifikasi push. Notifikasi dalam aplikasi (halaman Notifikasi) dan email tetap jalan.
- Scan barcode/QR dengan kamera DITUNDA untuk fase 1. Sembunyikan tombol Scan di web.
- Unggah foto dan file memakai pemilih file biasa.
- Chat: muat ulang pesan berkala (misalnya tiap 10 detik) saat halaman chat terbuka.
- Website harus nyaman di HP (mobile-first) dan di komputer.

## 7. Alamat & domain
- Selama pengembangan dan uji, pakai alamat bawaan Emergent.
- Domain utama pusatgrosirsidoarjo.com (saat ini masih WooCommerce) baru diarahkan ke website ini SETELAH saya menguji dan menyetujui website baru. Saya sudah menyimpan cadangan data website lama.
- Setelah disetujui: deploy, lalu hubungkan domain sendiri lewat pengaturan domain Emergent (ikuti petunjuk DNS dari Emergent di registrar domain saya), dan pastikan HTTPS aktif.
- Setelah domain aktif, saya akan meminta perubahan di proyek aplikasi HP agar: kode QR toko cabang mengarah ke `https://pusatgrosirsidoarjo.com/shop/<store_id>`, dan alamat callback Accurate serta pengaturan login Google mengikuti domain baru bila perlu.

## 8. Akun untuk menguji (data uji di server live; ganti kata sandi setelah peluncuran)
- Super Admin: admin@pgs.id
- Admin cabang Jombang: jombang@pgs.id
- Admin cabang Jember: jember@pgs.id
(Kata sandi akan saya berikan langsung saat diminta.)

## 9. Urutan kerja yang saya harapkan
1. Sambungkan ke server live dan pastikan login, katalog, dan halaman toko cabang tampil dengan data asli.
2. Selesaikan tampilan pelanggan sampai checkout dan pembayaran.
3. Selesaikan Admin Panel dan Seller Center.
4. Uji menyeluruh, lalu tunjukkan ke saya sebelum deploy dan sebelum domain diarahkan.
