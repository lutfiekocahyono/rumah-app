#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================
## Iteration 7 — Komplain & Refund (saldo) + Chat Pembeli–Toko
- backend/support.py: wallet (/api/wallet), complaints (/api/complaints, /seller/complaints, /admin/complaints, /complaints/{id}, /messages, /escalate, /decide), chat (/api/chats, /seller/chats, /chats/unread, /chats/{id}, /chats/{id}/messages)
- checkout: use_balance + payment_method "saldo"; balance returned on cancel/expired/failed
- Frontend: /wallet, /complaint (scope=mine|store|admin), /complaint/new?order=, /complaint/[id], /chat (side=store), /chat/[id]; buttons on order detail & seller order detail; menus in Akun, Admin, Seller

## Iteration 27 — Editor Produk Tahap 3 (Duplikat, Autosave, Edit Massal, Impor/Ekspor Excel)
- backend/product_bulk.py: GET /api/product-editor/products (list, q/status/store_id/skip), POST /api/product-editor/bulk (price_mode set|up_pct|down_pct|up|down, stock_mode set|add|sub, status), GET /api/product-editor/export (?template=true), POST /api/product-editor/import (multipart file .xlsx, ?commit=false preview / true apply; rows with ID update (only changed fields validated, unchanged = "same"), rows without ID create, incomplete new rows -> drafts; sheet Variasi updates variant price/stock/sku/active)
- product_editor.py: POST /api/product-editor/products/{id}/duplicate -> new draft "(Salinan)", sku cleared
- Frontend: /product-editor/list (select, bulk bar, dialogs, export, import), editor autosave 4s after change (pe-autosave), Duplikat button (pe-duplicate), resume-draft banner when editing a product with an autosaved draft.

## Iteration 28 — Impor format website + pencocokan kolom + template contoh
- product_bulk.py: import accepts .xlsx and .csv; WooCommerce/website column aliases (ID, Type, SKU, Name, Published, Short description, Description, Stock, Sale price, Regular price, Categories "A > B", Images, Weight (kg)->gram, Length/Width/Height (cm)); website numeric ID 9849 -> pgs-9849; HTML descriptions cleaned; Type=variation rows skipped; template rows with SKU "CONTOH-..." skipped. Response adds columns[{sheet,header,field,label}], missing[], format.
- Template: 2 example rows taken from real catalogue (orange), new sheet "Petunjuk Kolom" (wajib/format/contoh), export adds "Link Produk di Website (info)" column (permalink, not imported).
- Frontend import dialog: accepts .csv, shows "Pencocokan kolom" (import-columns, import-col-ok/unknown, import-missing) before Terapkan.

## Iteration 29 — Riwayat Harga & Stok
- backend/history.py: collection price_history {log_id, product_id, product_name, store_id, user_id, user_name, user_role, source(editor|bulk|import|stock|tiers), changes[{field,label,kind,variant,before,after}], kinds, at}. GET /api/history/price-stock?store_id&product_id&q&kind=price|stock&skip&limit — admin all stores (store filter optional); store owner/branch admin only own store (other store_id -> 403); customers 403.
- Recorded from: product-editor publish (edit), /product-editor/bulk, /product-editor/import (product + Variasi rows), PUT /seller/inventory/{id} (branch stock under the branch store_id), PUT /admin/products/{id}/tiers.
- Frontend: /product-editor/history (sidebar "Riwayat Harga & Stok", filters, admin store pills, ?product= filter), editor button pe-history.
- "URL Foto"/"Maks. Beli" headers recognized (fixed iter 28).

## Iteration 30 — Harga grosir per produk (global dihapus)
- pricing.py rewritten: product.tier_prices {langsung|pengecer|reseller: [{min_qty, price (Rupiah)}]}; langsung without qty-1 row = product price; pengecer/reseller without rows fall back to langsung table. No global discounts, no store restriction.
- One-time migration (settings key pricing_per_product): owner's former global (Pengecer 3%, Reseller 5%, qty 6 -2%, qty 12 -4%) copied to all 6618 pgs-official products as rupiah tiers; settings 'pricing' deleted. /api/admin/pricing GET/PUT removed; Admin menu "Pengaturan Harga" removed (admin index + akun tab); screen app/admin/pricing.tsx deleted.
- Product editor: ProductForm.tier_prices + validation (unique qty, price>=100, larger qty not more expensive; only non-variant); new section WholesaleSection (testIDs pe-wholesale, pe-tier-type-{t}, pe-tier-row-i, pe-tier-qty-i, pe-tier-price-i, pe-tier-range-i, pe-tier-del-i, pe-tier-add, pe-tier-copy, pe-tier-fallback, pe-tier-implicit, pe-tier-error). to_product saves tier_prices (variants -> {}).
- Bulk edit price (pct/up/down) also scales tiers; history snap includes tier_prices.

## Iteration 31 — Ekspor Riwayat + Menu bawah global + Pencarian atas + Scan
- history.py: GET /api/history/price-stock accepts date_from/date_to (YYYY-MM-DD, WIB, inclusive; bad format 400). GET /api/history/price-stock/export -> xlsx sheets Riwayat (Tanggal, Jam WIB, Toko, Produk, ID, Variasi, Perubahan, Sebelum, Sesudah, Selisih, Oleh, Peran, Sumber) + Ringkasan; same access rules (branch only own store, other store 403).
- Frontend history: Periode laporan (ph-range-this/last/all, ph-date-from/to), ph-export button.
- src/components/app-chrome.tsx in root _layout: global-search-bar (top, hidden on /, /search, /scan) + global-bottom-nav (tab-home, tab-kategori, tab-scan center, tab-keranjang w/ cart-tab-badge, tab-akun) on all pages except /login, /register, /forgot-password, /checkout. Tabs' own tab bar removed.
- /scan screen: mode Barcode Produk (GET /api/products/by-code/{code}: product_id, barcode, SKU, variant SKU, or product link) and Kode Ambil Pesanan (only for store owners/branch admins/Super Admin): POST /api/seller/pickup/lookup {code}, POST /api/seller/pickup/complete {code} (paid/cod -> processing -> completed; Super Admin any store, branch admin own store). Camera permission flow + manual input (scan-code-input, scan-code-submit).
- Editor: new Barcode field (pe-barcode) saved as product.barcode.

## Iteration 32 — Scan QR link fix + Accurate Online Tahap 1
- BUG FIX: QR product link 404. Backend: GET /api/products/by-code?code=<urlencoded> (query param) + /api/products/by-code/{code:path}; both resolve 'https://.../product/pgs-9849' -> pgs-9849. Frontend scan.tsx: scanned/typed text containing /product/<id> opens /product/<id> directly; other codes use query-param endpoint.
- Scan used by buyers (barcode mode only) and cashiers (mode switch). Manual input fallback when camera denied.
- backend/accurate.py (admin only): GET/PUT/DELETE /api/admin/accurate/settings (api_token & signature_secret encrypted with Fernet; response only hints ••••last4, never secrets; blank fields keep saved keys), POST /api/admin/accurate/test (real call to https://account.accurate.id/api/api-token.do; fake keys -> 400 'Kunci API ditolak Accurate'), GET /api/admin/accurate/warehouses, PUT /api/admin/accurate/warehouse-map, GET /api/admin/accurate/items (read-only). Client blocks any save/delete endpoint (phase 1 read-only).
- Frontend /admin/accurate (menu "Integrasi Accurate Online" in Admin): masked inputs, Simpan Kunci, Uji Koneksi, status, gudang mapping, item preview.

## Iteration 34 — QR Kode Ambil
- app/order/[id].tsx: pickup card shows QR (react-native-qrcode-svg, value "PGSAMBIL-<pickup_code>", testID order-pickup-qr) above the 6-digit code, only while order is open (not cancelled/expired/failed/completed).
- app/scan.tsx: scanned/typed "PGSAMBIL-<digits>" -> cashier: auto switches to pickup mode and looks up the order; buyer (no store): message "Ini kode ambil pesanan — tunjukkan ke kasir toko." Backend lookup strips non-digits.

## Iteration 35 — Panduan Accurate, tombol Chat produk, teks COD selesai
- /admin/accurate: AccurateGuide card (testIDs accurate-guide, accurate-copy-app, accurate-copy-callback (+ -value), accurate-open-dev, accurate-guide-note): 4 steps, App URL = EXPO_PUBLIC_BACKEND_URL, Callback = <base>/api/accurate/callback (GET returns small HTML page), note to replace after launch. Copy via expo-clipboard.
- Product detail bottom bar: pd-chat-btn left of add-to-cart-btn; guest -> /login; logged in -> POST /api/chats {store_id: selected branch for pgs-official products, else product.store_id} -> /chat/{conv_id}.
- Order page: COD note (order-cod-note): completed -> "Lunas — dibayar tunai (COD) saat pengambilan."; cancelled/expired/failed -> "Pesanan dibatalkan, tidak ada pembayaran."; otherwise "Bayar tunai (COD) saat mengambil pesanan."

## Iteration 36 — Chat kartu produk + Accurate Tahap 2 (tarik data & faktur)
- Chat: POST /api/chats with product_id now auto-posts a buyer message "Halo, saya ingin bertanya tentang produk ini:\n<nama lengkap>" with message.product {product_id,name,image,price,sku}; not repeated if the latest message is already the same product card. Chat screen renders card (testID chat-product-card, chat-product-name), tap -> /product/{id}.
- backend/accurate_sync.py (admin): POST /api/admin/accurate/sync/preview {prices,stocks,new_products} -> reads all Accurate items (+ per mapped warehouse stock), matches SKU of pgs-official products (variant products skipped), stores preview in accurate_sync; GET /api/admin/accurate/sync/{id}; POST /api/admin/accurate/sync/{id}/apply {skip:[keys], skip_new:[item no]} applies once (2h expiry; re-apply 400), skips values changed after preview (conflict), records price_history source "accurate", new items created status inactive source accurate.
- Invoices: PUT /api/admin/accurate/invoice-settings {customer_no, shipping_item_no}; GET /api/admin/accurate/orders?sent=false|true (paid/processing/shipped/completed; COD only completed); GET /api/admin/accurate/invoice/{order_id} preview (lines with SKU, warehouse from map, problems list); POST same with {confirm:true} -> Accurate sales-invoice/save.do (number = order_id), lock prevents double send (409), failure stored status failed.
- Mock Accurate host for tests: backend/tests/accurate_mock.py (python tests/accurate_mock.py 9911); settings doc key=accurate currently points host to http://127.0.0.1:9911 with fake encrypted keys and warehouse_map.
- Frontend /admin/accurate: sections 4 (testIDs accurate-sync, accurate-opt-*, accurate-sync-preview, accurate-preview, accurate-change-*, accurate-new-*, accurate-sync-apply, accurate-sync-done) and 5 (accurate-invoices, accurate-customer-no, accurate-shipping-item, accurate-invoice-settings-save, accurate-orders-tab-todo/sent, accurate-order-{id}, accurate-invoice-preview, accurate-invoice-send, accurate-invoice-sent).
