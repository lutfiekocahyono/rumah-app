import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";
import { uploadForm, type LocalFile } from "@/src/utils/upload";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

const TOKEN_KEY = "pgs_auth_token";
const GUEST_KEY = "pgs_guest_id";

let memToken: string | null = null;
let memGuest: string | null = null;

export async function getToken(): Promise<string | null> {
  if (memToken) return memToken;
  try {
    const v = Platform.OS === "web" ? (globalThis as any).localStorage?.getItem(TOKEN_KEY) : await SecureStore.getItemAsync(TOKEN_KEY);
    memToken = v ?? null;
    return memToken;
  } catch {
    return null;
  }
}

export async function setToken(token: string | null) {
  memToken = token;
  if (Platform.OS === "web") {
    if (token) (globalThis as any).localStorage?.setItem(TOKEN_KEY, token);
    else (globalThis as any).localStorage?.removeItem(TOKEN_KEY);
    return;
  }
  if (token) await SecureStore.setItemAsync(TOKEN_KEY, token);
  else await SecureStore.deleteItemAsync(TOKEN_KEY);
}

export async function getGuestId(): Promise<string> {
  if (memGuest) return memGuest;
  try {
    const existing = Platform.OS === "web"
      ? (globalThis as any).localStorage?.getItem(GUEST_KEY)
      : await SecureStore.getItemAsync(GUEST_KEY);
    if (existing) {
      memGuest = existing;
      return existing;
    }
  } catch {}
  const nid = `g_${Math.random().toString(36).slice(2, 10)}_${Date.now().toString(36)}`;
  memGuest = nid;
  try {
    if (Platform.OS === "web") (globalThis as any).localStorage?.setItem(GUEST_KEY, nid);
    else await SecureStore.setItemAsync(GUEST_KEY, nid);
  } catch {}
  return nid;
}

let currentStore = "pgs-official";
/** Branch chosen by the buyer (PGS Sidoarjo / Mitra Jombang / Mitra Jember); sent with every request. */
export const setCurrentStore = (id: string) => { currentStore = id; };
/** Requests made by a branch store page: lists only show products with a price set for that branch. */
const sc = (shop?: boolean): RequestInit => (shop ? { headers: { "X-Shop-Page": "1" } } : {});

async function headers(): Promise<Record<string, string>> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const token = await getToken();
  if (token) h["Authorization"] = `Bearer ${token}`;
  h["X-Guest-Id"] = await getGuestId();
  h["X-Store-Id"] = currentStore;
  return h;
}

/** Query string without empty values. */
function qs(p: Record<string, string | number | boolean | null | undefined>): string {
  return Object.entries(p).filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = `${BASE}/api${path}`;
  const res = await fetch(url, { ...init, headers: { ...(await headers()), ...(init.headers || {}) } });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    let fieldErrors: Record<string, string> | undefined;
    try {
      const data = await res.json();
      const d = data.detail;
      msg = Array.isArray(d) ? d.map((x: any) => x?.msg).filter(Boolean).join(", ") || msg : (typeof d === "string" ? d : d?.message || data.message || msg);
      if (d && typeof d === "object" && !Array.isArray(d) && d.errors) fieldErrors = d.errors; // field -> message (form validation)
    } catch {}
    throw Object.assign(new Error(msg), { status: res.status, errors: fieldErrors });
  }
  return (await res.json()) as T;
}

export const api = {
  // auth
  register: (email: string, password: string, name: string) =>
    req<{ token: string; user: User }>("/auth/register", { method: "POST", body: JSON.stringify({ email, password, name }) }),
  login: (email: string, password: string) =>
    req<{ token: string; user: User }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => req<User>("/auth/me"),
  googleSession: (session_id: string) =>
    req<{ token: string; user: User }>("/auth/session", { method: "POST", body: JSON.stringify({ session_id }) }),
  store: () => req<StoreInfo>("/store"),

  // catalog
  categories: (parent?: string) => req<Category[]>(`/categories${parent ? `?parent=${encodeURIComponent(parent)}` : ""}`),
  allCategories: () => req<Category[]>("/categories?all=true"),
  productCount: () => req<{ count: number }>("/products/count"),
  products: (params: ProductQuery = {}, shop?: boolean) => req<Product[]>(`/products?${productQs(params)}`, sc(shop)),
  productFacets: (params: ProductQuery = {}, shop?: boolean) => req<ProductFacets>(`/products/facets?${productQs(params)}`, sc(shop)),
  product: (id: string) => req<Product>(`/products/${id}`),

  // cart
  getCart: () => req<Cart>("/cart"),
  addCart: (product_id: string, quantity = 1, variant_id?: string | null) =>
    req<Cart>("/cart/items", { method: "POST", body: JSON.stringify({ product_id, quantity, variant_id }) }),
  // key = cart line (product_id, or product_id::variant_id)
  updateCart: (key: string, quantity: number) =>
    req<Cart>(`/cart/items/${encodeURIComponent(key)}`, { method: "PUT", body: JSON.stringify({ quantity }) }),
  removeCart: (key: string) => req<Cart>(`/cart/items/${encodeURIComponent(key)}`, { method: "DELETE" }),
  clearCart: () => req<Cart>("/cart", { method: "DELETE" }),

  // wishlist
  getWishlist: () => req<{ items: Product[] }>("/wishlist"),
  addWishlist: (product_id: string) => req<{ items: Product[] }>(`/wishlist/${product_id}`, { method: "POST" }),
  removeWishlist: (product_id: string) => req<{ items: Product[] }>(`/wishlist/${product_id}`, { method: "DELETE" }),

  // orders
  checkout: (body: CheckoutPayload) => req<Order>("/checkout", { method: "POST", body: JSON.stringify(body) }),
  orders: () => req<Order[]>("/orders"),
  order: (id: string) => req<Order>(`/orders/${id}`),
  refreshOrder: (id: string) => req<Order>(`/orders/${id}/refresh`, { method: "POST" }),

  // admin
  adminCustomers: (q = "") => req<User[]>(`/admin/customers${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  adminSetCustomerType: (user_id: string, customer_type: CustomerType) =>
    req<User>(`/admin/customers/${user_id}`, { method: "PUT", body: JSON.stringify({ customer_type }) }),
  adminStats: () => req<AdminStats>("/admin/stats"),
  adminOrders: (status?: string, q?: string) => {
    const qs = new URLSearchParams();
    if (status) qs.set("status", status);
    if (q) qs.set("q", q);
    const s = qs.toString();
    return req<Order[]>(`/admin/orders${s ? "?" + s : ""}`);
  },
  adminOrder: (id: string) => req<Order>(`/admin/orders/${id}`),
  adminSetOrderStatus: (id: string, status: Order["status"]) =>
    req<Order>(`/admin/orders/${id}/status`, { method: "PUT", body: JSON.stringify({ status }) }),

  // homepage promo
  banners: () => req<Banner[]>("/banners"),
  homeSettings: () => req<HomeSettings>("/home-settings"),
  flashSale: (shop?: boolean) => req<FlashSale>("/flash-sale", sc(shop)),
  vouchers: () => req<Voucher[]>("/vouchers"),
  myVouchers: () => req<Voucher[]>("/vouchers/mine"),
  claimVoucher: (code: string) => req<Voucher>(`/vouchers/${encodeURIComponent(code)}/claim`, { method: "POST" }),
  applyVoucher: (code: string) => req<{ code: string; title: string; discount: number }>("/vouchers/apply", { method: "POST", body: JSON.stringify({ code }) }),
  trackView: (product_id: string) => req<{ ok: boolean }>(`/activity/view/${product_id}`, { method: "POST" }),
  recommendations: (skip = 0, limit = 20) => req<Product[]>(`/recommendations?skip=${skip}&limit=${limit}`),
  homeSections: (shop?: boolean) => req<HomeFeed>("/home/sections", sc(shop)),
  moreRecommended: (skip: number, limit = 20, shop?: boolean) => req<Product[]>(`/home/sections/recommended?skip=${skip}&limit=${limit}`, sc(shop)),
  sellerHomeSections: () => req<HomeSectionsSettings>("/seller/home-sections"),
  saveSellerHomeSections: (s: HomeSectionsInput) => req<HomeSectionsSettings>("/seller/home-sections", { method: "PUT", body: JSON.stringify(s) }),
  adminHomeSections: (storeId: string) => req<HomeSectionsSettings>(`/admin/home-sections/${storeId}`),
  saveAdminHomeSections: (storeId: string, s: HomeSectionsInput) => req<HomeSectionsSettings>(`/admin/home-sections/${storeId}`, { method: "PUT", body: JSON.stringify(s) }),
  copyHomePins: (storeId: string) => req<{ copied_to: string[]; counts: Record<HomeSectionKey, number> }>(`/admin/home-sections/${storeId}/copy-pins`, { method: "POST" }),

  // admin promo
  adminBanners: () => req<Banner[]>("/admin/banners"),
  adminSaveBanner: (b: BannerInput, id?: string) =>
    req<Banner>(id ? `/admin/banners/${id}` : "/admin/banners", { method: id ? "PUT" : "POST", body: JSON.stringify(b) }),
  adminDeleteBanner: (id: string) => req<{ ok: boolean }>(`/admin/banners/${id}`, { method: "DELETE" }),
  adminFlashSale: () => req<AdminFlashSale>("/admin/flash-sale"),
  flashSchedules: () => req<FlashSchedule[]>("/flash-sale/schedules"),
  saveFlashSchedule: (storeId: string, b: { follow: boolean; starts_at: string | null; ends_at: string | null }) =>
    req<FlashSchedule>(`/flash-sale/schedules/${storeId}`, { method: "PUT", body: JSON.stringify(b) }),
  adminSaveFlashSale: (f: { title: string; active: boolean; ends_at: string; items: { product_id: string; flash_price: number; branch_prices: Record<string, number> }[] }) =>
    req<AdminFlashSale>("/admin/flash-sale", { method: "PUT", body: JSON.stringify(f) }),
  adminVouchers: () => req<Voucher[]>("/admin/vouchers"),
  adminSaveVoucher: (v: VoucherInput, isNew: boolean) =>
    req<Voucher>(isNew ? "/admin/vouchers" : `/admin/vouchers/${v.code}`, { method: isNew ? "POST" : "PUT", body: JSON.stringify(v) }),
  adminDeleteVoucher: (code: string) => req<{ ok: boolean }>(`/admin/vouchers/${code}`, { method: "DELETE" }),
  adminSaveHomeSettings: (s: Omit<HomeSettings, "key">) => req<HomeSettings>("/admin/home-settings", { method: "PUT", body: JSON.stringify(s) }),
  adminUpload: (file: LocalFile) => uploadTo("/admin/upload", file),

  // account
  verifyEmailRequest: () => req<{ message: string }>("/auth/verify-email/request", { method: "POST" }),
  verifyEmailConfirm: (code: string) => req<User>("/auth/verify-email/confirm", { method: "POST", body: JSON.stringify({ code }) }),
  phoneRequest: (phone: string) => req<{ message: string; phone: string; dev_code?: string }>("/auth/phone/request", { method: "POST", body: JSON.stringify({ phone }) }),
  phoneConfirm: (code: string) => req<User>("/auth/phone/confirm", { method: "POST", body: JSON.stringify({ code }) }),
  resetRequest: (email: string) => req<{ message: string }>("/auth/password-reset/request", { method: "POST", body: JSON.stringify({ email }) }),
  resetConfirm: (email: string, code: string, new_password: string) =>
    req<{ message: string }>("/auth/password-reset/confirm", { method: "POST", body: JSON.stringify({ email, code, new_password }) }),
  changePassword: (current_password: string, new_password: string) =>
    req<{ token: string; user: User }>("/auth/password/change", { method: "POST", body: JSON.stringify({ current_password, new_password }) }),
  updateProfile: (p: { name: string; gender: string; birthdate: string }) => req<User>("/me/profile", { method: "PUT", body: JSON.stringify(p) }),
  uploadAvatar: async (file: LocalFile) => (await uploadTo("/me/avatar", file)) as unknown as User,
  addresses: () => req<Address[]>("/me/addresses"),
  saveAddress: (a: AddressInput, id?: string) =>
    req<Address[]>(id ? `/me/addresses/${id}` : "/me/addresses", { method: id ? "PUT" : "POST", body: JSON.stringify(a) }),
  deleteAddress: (id: string) => req<Address[]>(`/me/addresses/${id}`, { method: "DELETE" }),
  activity: () => req<{ logs: ActivityLog[]; recently_viewed: { product_id: string; name: string; image: string; price: number }[] }>("/me/activity"),
  settings: () => req<AccountSettings>("/me/settings"),
  saveSettings: (s: AccountSettings) => req<AccountSettings>("/me/settings", { method: "PUT", body: JSON.stringify(s) }),
  notifications: () => req<AppNotification[]>("/notifications"),
  pushConfig: () => req<{ enabled: boolean }>("/push/config"),
  registerPush: (user_id: string, platform: string, device_token: string) =>
    req<{ status: string }>("/register-push", { method: "POST", body: JSON.stringify({ user_id, platform, device_token }) }),
  adminPush: () => req<PushStatus>("/admin/push"),
  adminSetPush: (enabled: boolean) => req<PushStatus>("/admin/push", { method: "PUT", body: JSON.stringify({ enabled }) }),
  productUpdates: (id: string) => req<ProductUpdates>(`/product-updates/${id}`),
  unreadCount: () => req<{ count: number }>("/notifications/unread-count"),
  readAll: () => req<{ ok: boolean }>("/notifications/read-all", { method: "POST" }),
  readOne: (id: string) => req<{ ok: boolean }>(`/notifications/${id}/read`, { method: "POST" }),

  // seller
  myStore: () => req<Store | null>("/me/store"),
  openStore: (s: StoreInput) => req<Store>("/stores", { method: "POST", body: JSON.stringify(s) }),
  editStore: (s: StoreInput) => req<Store>("/me/store", { method: "PUT", body: JSON.stringify(s) }),
  storePage: (id: string) => req<Store>(`/stores/${id}`),
  shopPage: (id: string) => req<ShopPage>(`/stores/${id}/page`),
  shopCategories: (id: string, parent?: string) => req<Category[]>(`/stores/${id}/categories${parent ? `?${qs({ parent })}` : ""}`),
  suggest: (q: string) => req<{ products: { product_id: string; name: string; image: string }[]; brands: string[]; categories: { category_id: string; name: string }[] }>(`/products/suggest?${qs({ q })}`),
  storeAppearance: () => req<StoreAppearance[]>("/store-appearance"),
  saveStoreAppearance: (id: string, b: Omit<StoreAppearance, "store_id" | "name" | "city" | "featured"> & { featured_ids: string[] }) =>
    req<StoreAppearance>(`/store-appearance/${id}`, { method: "PUT", body: JSON.stringify(b) }),
  sellerProducts: () => req<Product[]>("/seller/products"),
  sellerSaveProduct: (p: SellerProductInput, id?: string) =>
    req<Product>(id ? `/seller/products/${id}` : "/seller/products", { method: id ? "PUT" : "POST", body: JSON.stringify(p) }),
  sellerDeleteProduct: (id: string) => req<{ ok: boolean }>(`/seller/products/${id}`, { method: "DELETE" }),
  sellerUpload: (file: LocalFile) => uploadTo("/seller/upload", file),
  editorContext: () => req<EditorContext>("/product-editor/context"),
  editorDrafts: () => req<ProductDraft[]>("/product-editor/drafts"),
  editorDraft: (id: string) => req<ProductDraft>(`/product-editor/drafts/${id}`),
  editorSaveDraft: (b: { draft_id?: string | null; product_id?: string | null; store_id?: string | null; data: ProductForm }) =>
    req<ProductDraft>("/product-editor/drafts", { method: "POST", body: JSON.stringify(b) }),
  editorDeleteDraft: (id: string) => req<{ ok: boolean }>(`/product-editor/drafts/${id}`, { method: "DELETE" }),
  editorProduct: (id: string) => req<{ product_id: string; store_id: string; data: ProductForm }>(`/product-editor/products/${id}`),
  editorPublish: (b: { draft_id?: string | null; product_id?: string | null; store_id?: string | null; data: ProductForm }) =>
    req<{ product_id: string; store_id: string; status: "active" | "inactive" }>("/product-editor/publish", { method: "POST", body: JSON.stringify(b) }),
  editorList: (p: { store_id?: string | null; q?: string; status?: string; skip?: number }) =>
    req<{ total: number; items: EditorListItem[]; store_id: string }>(`/product-editor/products?${qs({ ...p, limit: 30 })}`),
  editorDuplicate: (id: string) => req<ProductDraft>(`/product-editor/products/${id}/duplicate`, { method: "POST" }),
  weightSummary: (store_id?: string | null, kind: EstimateKind = "weight") => req<{ missing: number; estimated: number }>(`/product-editor/${kind}/summary?${qs({ store_id })}`),
  weightPreview: (store_id?: string | null, kind: EstimateKind = "weight") => req<WeightPreview>(`/product-editor/${kind}/preview?${qs({ store_id })}`, { method: "POST" }),
  weightApply: (id: string, skip: string[], overrides: Record<string, number | number[]>, kind: EstimateKind = "weight") =>
    req<{ saved: number }>(`/product-editor/${kind}/${id}/apply`, { method: "POST", body: JSON.stringify({ skip, overrides }) }),
  uncatSummary: (store_id?: string | null) => req<{ count: number }>(`/product-editor/uncategorized/summary?${qs({ store_id })}`),
  uncatPreview: (store_id?: string | null) => req<CategoryPreview>(`/product-editor/uncategorized/preview?${qs({ store_id })}`, { method: "POST" }),
  uncatApply: (id: string, skip: string[], overrides: Record<string, string>) =>
    req<{ saved: number }>(`/product-editor/uncategorized/${id}/apply`, { method: "POST", body: JSON.stringify({ skip, overrides }) }),
  branchBulkPreview: (b: { store_id: string | null; mode: "pct" | "rp"; value: number; tiers: boolean; q: string }) =>
    req<BranchBulkPreview>("/branch-prices/bulk/preview", { method: "POST", body: JSON.stringify(b) }),
  branchBulkApply: (id: string, confirmDown = false) => req<{ saved: number }>(`/branch-prices/bulk/${id}/apply`, { method: "POST", body: JSON.stringify({ confirm_down: confirmDown }) }),
  branchExportUrl: (store_id: string | null) => `${BASE}/api/branch-prices/export?${qs({ store_id })}`,
  branchImport: async (file: LocalFile, store_id: string | null): Promise<BranchBulkPreview> => {
    const token = await getToken();
    const res = await uploadForm(`${BASE}/api/branch-prices/import?${qs({ store_id })}`, { headers: token ? { Authorization: `Bearer ${token}` } : {}, files: { file } });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
    return data as BranchBulkPreview;
  },
  branchPrices: (store_id: string | null, q = "", skip = 0) => req<BranchPriceList>(`/branch-prices?${qs({ store_id, q, skip, limit: 40 })}`),
  setBranchPrice: (id: string, b: { store_id: string | null; price: number; original_price: number; tier_prices: Record<string, { min_qty: number; price: number }[]> }) =>
    req<BranchPriceItem>(`/branch-prices/${id}`, { method: "PUT", body: JSON.stringify(b) }),
  branchCopyPreview: (rules: BranchCopyRule[]) =>
    req<BranchCopyPreview>("/admin/branch-copy/preview", { method: "POST", body: JSON.stringify({ rules }) }),
  branchCopyApply: (id: string, confirmDown = false) => req<{ branches: { store_id: string; store_name: string; updated: number }[] }>(`/admin/branch-copy/${id}/apply`, { method: "POST", body: JSON.stringify({ confirm_down: confirmDown }) }),
  nearestStores: (lat: number, lng: number) => req<NearestStores>(`/branches/nearest?${qs({ lat, lng })}`),
  saveLocation: (lat: number, lng: number, accuracy: number | null, platform: string) =>
    req<{ saved: boolean }>("/location", { method: "POST", body: JSON.stringify({ lat, lng, accuracy, platform }) }),
  customerLocations: (days: number, guests: boolean) => req<CustomerLocations>(`/admin/customer-locations?${qs({ days, guests })}`),
  adminFonnte: () => req<FonnteStatus>("/admin/fonnte"),
  adminSetFonnte: (b: { token?: string; owner_whatsapp?: string }) => req<FonnteStatus>("/admin/fonnte", { method: "PUT", body: JSON.stringify(b) }),
  adminTestFonnte: (token?: string) => req<FonnteTest>("/admin/fonnte/test", { method: "POST", body: JSON.stringify({ token: token || null }) }),
  adminTestFonnteOtp: (phone: string) => req<{ ok: boolean; message: string }>("/admin/fonnte/test-otp", { method: "POST", body: JSON.stringify({ phone }) }),
  editorBulk: (b: BulkEdit) => req<{ updated: number; skipped: { product_id: string; name: string; reason: string }[] }>("/product-editor/bulk", { method: "POST", body: JSON.stringify(b) }),
  editorImport: async (file: LocalFile, storeId: string | null, commit: boolean): Promise<ImportReport> => {
    const token = await getToken();
    const res = await uploadForm(`${BASE}/api/product-editor/import?${qs({ store_id: storeId, commit })}`, { headers: token ? { Authorization: `Bearer ${token}` } : {}, files: { file } });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
    return data as ImportReport;
  },
  editorExportUrl: (storeId: string | null, template = false) => `${BASE}/api/product-editor/export?${qs({ store_id: storeId, template })}`,
  priceHistory: (p: { store_id?: string | null; product_id?: string | null; q?: string; kind?: string; date_from?: string; date_to?: string; skip?: number }) =>
    req<{ total: number; items: PriceLog[] }>(`/history/price-stock?${qs({ ...p, limit: 30 })}`),
  priceHistoryExportUrl: (p: { store_id?: string | null; product_id?: string | null; q?: string; kind?: string; date_from?: string; date_to?: string }) =>
    `${BASE}/api/history/price-stock/export?${qs(p)}`,
  productByCode: (code: string) => req<{ product_id: string; name: string }>(`/products/by-code?${qs({ code })}`),
  accurateSettings: () => req<AccurateSettings>("/admin/accurate/settings"),
  accurateSave: (b: { api_token: string; signature_secret: string; database_id: string }) => req<AccurateSettings>("/admin/accurate/settings", { method: "PUT", body: JSON.stringify(b) }),
  accurateDelete: () => req<AccurateSettings>("/admin/accurate/settings", { method: "DELETE" }),
  accurateTest: () => req<AccurateSettings>("/admin/accurate/test", { method: "POST" }),
  accurateWarehouses: () => req<{ items: { id: number; name: string; description: string; suspended: boolean }[] }>("/admin/accurate/warehouses"),
  accurateSaveMap: (warehouse_map: Record<string, string>) => req<AccurateSettings>("/admin/accurate/warehouse-map", { method: "PUT", body: JSON.stringify({ warehouse_map }) }),
  accurateItems: (page: number, warehouse: string) =>
    req<{ items: AccurateItem[]; page: number; page_count: number; total: number }>(`/admin/accurate/items?${qs({ page, warehouse })}`),
  accurateSyncPreview: (b: { prices: boolean; stocks: boolean; new_products: boolean }) => req<AccuratePreview>("/admin/accurate/sync/preview", { method: "POST", body: JSON.stringify(b) }),
  accurateSyncApply: (id: string, skip: string[], skip_new: string[]) =>
    req<{ preview_id: string; result: AccurateSyncResult }>(`/admin/accurate/sync/${id}/apply`, { method: "POST", body: JSON.stringify({ skip, skip_new }) }),
  accurateInvoiceSettings: (customer_no: string, shipping_item_no: string) =>
    req<{ customer_no: string; shipping_item_no: string }>("/admin/accurate/invoice-settings", { method: "PUT", body: JSON.stringify({ customer_no, shipping_item_no }) }),
  accurateOrders: (sent: boolean, page = 1) => req<{ total: number; page: number; items: AccurateOrderRow[] }>(`/admin/accurate/orders?${qs({ sent, page })}`),
  accurateInvoice: (order_id: string) => req<AccurateInvoice>(`/admin/accurate/invoice/${order_id}`),
  accurateSendInvoice: (order_id: string) => req<AccurateInvoice>(`/admin/accurate/invoice/${order_id}`, { method: "POST", body: JSON.stringify({ confirm: true }) }),
  pickupLookup: (code: string) => req<Order>("/seller/pickup/lookup", { method: "POST", body: JSON.stringify({ code }) }),
  pickupComplete: (code: string) => req<Order>("/seller/pickup/complete", { method: "POST", body: JSON.stringify({ code }) }),
  adminStores: (status?: string) => req<Store[]>(`/admin/stores${status ? `?status=${status}` : ""}`),
  adminSetStoreStatus: (id: string, status: "active" | "rejected" | "suspended", note = "") =>
    req<Store>(`/admin/stores/${id}/status`, { method: "PUT", body: JSON.stringify({ status, note }) }),

  // branches, couriers, store orders, reports
  officialStores: () => req<Store[]>("/official-stores"),
  storeCouriers: (id: string) => req<Courier[]>(`/stores/${id}/couriers`),
  confirmReceived: (id: string) => req<Order>(`/orders/${id}/confirm`, { method: "POST" }),
  sellerInventory: (q = "", skip = 0) => req<InventoryItem[]>(`/seller/inventory?q=${encodeURIComponent(q)}&skip=${skip}&limit=40`),
  sellerSetStock: (id: string, stock: number) => req<{ stock: number }>(`/seller/inventory/${id}`, { method: "PUT", body: JSON.stringify({ stock }) }),
  sellerCouriers: () => req<Courier[]>("/seller/couriers"),
  sellerSaveCouriers: (couriers: Courier[]) => req<Courier[]>("/seller/couriers", { method: "PUT", body: JSON.stringify({ couriers }) }),
  adminCouriers: (id: string) => req<Courier[]>(`/admin/stores/${id}/couriers`),
  adminSaveCouriers: (id: string, couriers: Courier[]) => req<Courier[]>(`/admin/stores/${id}/couriers`, { method: "PUT", body: JSON.stringify({ couriers }) }),
  sellerOrders: (status?: string) => req<Order[]>(`/seller/orders${status ? `?status=${status}` : ""}`),
  sellerOrder: (id: string) => req<Order>(`/seller/orders/${id}`),
  sellerSetOrderStatus: (id: string, status: string, tracking_number = "") =>
    req<Order>(`/seller/orders/${id}/status`, { method: "PUT", body: JSON.stringify({ status, tracking_number }) }),
  sellerExtendOrder: (id: string, hours: number) => req<Order>(`/seller/orders/${id}/extend`, { method: "POST", body: JSON.stringify({ hours }) }),
  sellerReadyOrder: (id: string) => req<Order>(`/seller/orders/${id}/ready`, { method: "POST" }),
  sellerReport: () => req<Report>("/seller/report"),
  adminReport: () => req<{ all: Report; stores: (Report & { store_id: string; name: string })[] }>("/admin/report"),
  shippingSettings: () => req<ShippingSettings>("/admin/shipping-settings"),
  verifyShippingKey: () => req<ShippingSettings>("/admin/shipping/verify-key", { method: "POST" }),
  paymentSettings: () => req<PaymentSettings>("/admin/payment-settings"),
  savePaymentSettings: (b: { enabled: boolean; production: boolean; server_key: string | null; client_key: string }) =>
    req<PaymentSettings>("/admin/payment-settings", { method: "PUT", body: JSON.stringify(b) }),
  verifyMidtrans: () => req<PaymentSettings>("/admin/payment/verify-midtrans", { method: "POST" }),
  productAvailability: (id: string, area = "") => req<BranchSuggest>(`/products/${id}/availability?area=${encodeURIComponent(area)}`),
  suggestStores: (area: string, product_ids: string[] = [], quantities: number[] = []) =>
    req<BranchSuggest>("/stores/suggest", { method: "POST", body: JSON.stringify({ area, product_ids, quantities }) }),
  moveCart: (from_store_id: string, to_store_id: string) =>
    req<{ moved: number; skipped: string[] }>("/cart/move", { method: "POST", body: JSON.stringify({ from_store_id, to_store_id }) }),
  paymentMethods: () => req<{ midtrans: boolean; xendit: boolean; cod: boolean; midtrans_sandbox: boolean }>("/payments/methods"),
  saveShippingSettings: (s: Omit<ShippingSettings, "configured" | "key_hint"> & { api_key?: string | null }) =>
    req<ShippingSettings>("/admin/shipping-settings", { method: "PUT", body: JSON.stringify(s) }),
  adminDestinations: (q: string) => req<Destination[]>(`/admin/shipping/destinations?q=${encodeURIComponent(q)}`),
  shippingStatus: () => req<{ auto: boolean }>("/shipping/status"),
  destinations: (q: string) => req<{ auto: boolean; data: Destination[] }>(`/shipping/destinations?q=${encodeURIComponent(q)}`),
  shippingRates: (store_id: string, destination_id?: number | null) =>
    req<Courier[]>("/shipping/rates", { method: "POST", body: JSON.stringify({ store_id, destination_id: destination_id ?? null }) }),

  // saldo, komplain & refund, chat
  wallet: () => req<Wallet>("/wallet"),
  createComplaint: (b: { order_id: string; reason: ComplaintReason; description: string; refund_amount: number }) =>
    req<Complaint>("/complaints", { method: "POST", body: JSON.stringify(b) }),
  complaints: (scope: "mine" | "store" | "admin", status = "") =>
    req<Complaint[]>(`${scope === "mine" ? "/complaints" : scope === "store" ? "/seller/complaints" : "/admin/complaints"}${status ? `?status=${status}` : ""}`),
  complaint: (id: string) => req<Complaint>(`/complaints/${id}`),
  replyComplaint: (id: string, text: string) => req<Complaint>(`/complaints/${id}/messages`, { method: "POST", body: JSON.stringify({ text }) }),
  escalateComplaint: (id: string, text: string) => req<Complaint>(`/complaints/${id}/escalate`, { method: "POST", body: JSON.stringify({ text }) }),
  decideComplaint: (id: string, action: "refund" | "reject" | "resolve", amount = 0, note = "") =>
    req<Complaint>(`/complaints/${id}/decide`, { method: "POST", body: JSON.stringify({ action, amount, note }) }),
  startChat: (store_id: string, product_id?: string) => req<Conversation>("/chats", { method: "POST", body: JSON.stringify({ store_id, product_id }) }),
  sellerStartChat: (order_id: string) => req<Conversation>("/seller/chats", { method: "POST", body: JSON.stringify({ order_id }) }),
  chats: (side: "buyer" | "store") => req<Conversation[]>(side === "store" ? "/seller/chats" : "/chats"),
  chatUnread: () => req<{ buyer: number; store: number }>("/chats/unread"),
  chatThread: (id: string, after?: string) => req<ChatThread>(`/chats/${id}${after ? `?after=${encodeURIComponent(after)}` : ""}`),
  sendChat: (id: string, text: string) => req<ChatMessage>(`/chats/${id}/messages`, { method: "POST", body: JSON.stringify({ text }) }),
  quickReplies: () => req<{ items: QuickReply[] }>("/seller/quick-replies"),
  addQuickReply: (title: string, text: string) => req<QuickReply>("/seller/quick-replies", { method: "POST", body: JSON.stringify({ title, text }) }),
  editQuickReply: (id: string, title: string, text: string) => req<QuickReply>(`/seller/quick-replies/${id}`, { method: "PUT", body: JSON.stringify({ title, text }) }),
  deleteQuickReply: (id: string) => req<{ ok: boolean }>(`/seller/quick-replies/${id}`, { method: "DELETE" }),
};

export type Wallet = { balance: number; transactions: { tx_id: string; amount: number; kind: "refund" | "payment" | "return"; ref: string; note: string; created_at: string }[] };
export type ComplaintReason = "damaged" | "wrong_item" | "missing" | "not_received" | "other";
export const COMPLAINT_REASONS: { id: ComplaintReason; label: string }[] = [
  { id: "damaged", label: "Barang rusak" }, { id: "wrong_item", label: "Barang tidak sesuai" }, { id: "missing", label: "Barang kurang" },
  { id: "not_received", label: "Barang belum diterima" }, { id: "other", label: "Lainnya" },
];
export type ComplaintStatus = "open" | "escalated" | "refunded" | "rejected" | "resolved";
export const COMPLAINT_STATUS_LABEL: Record<ComplaintStatus, string> = {
  open: "Menunggu toko", escalated: "Ditangani Admin PGS", refunded: "Refund ke saldo", rejected: "Ditolak", resolved: "Selesai",
};
export type Complaint = {
  complaint_id: string; order_id: string; store_id: string; store_name: string; user_id: string; user_name: string;
  reason: ComplaintReason; reason_label: string; description: string; refund_amount: number; order_total: number; refunded: number; refundable: number;
  status: ComplaintStatus; decision: { action: string; amount: number; note: string; by: string; at: string } | null;
  messages: { by: "buyer" | "store" | "admin"; name: string; text: string; at: string }[];
  viewer: "buyer" | "store" | "admin"; cod_unpaid?: boolean; can_decide: boolean; can_escalate: boolean; can_reply: boolean; created_at: string; updated_at: string;
};
export type Conversation = { conv_id: string; user_id: string; user_name: string; store_id: string; store_name: string; last_text: string; last_at: string; last_sender?: "user" | "store"; unread_user: number; unread_store: number };
export type ChatMessage = { msg_id: string; conv_id: string; sender: "user" | "store"; text: string; created_at: string;
  product?: { product_id: string; name: string; image: string; price: number; sku: string } };
export type ChatThread = { conversation: Conversation; me: "user" | "store"; messages: ChatMessage[] };
export type QuickReply = { reply_id: string; title: string; text: string; order: number };

async function uploadTo(path: string, file: LocalFile): Promise<{ url: string }> {
  const token = await getToken();
  const res = await uploadForm(`${BASE}/api${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {}, files: { file } });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return (await res.json()) as { url: string };
}

/** Uploaded files come back as "/api/files/..." — make them absolute for <Image>. */
export const imgUrl = (u: string) => (u?.startsWith("/") ? `${BASE}${u}` : u);

export type Banner = { banner_id: string; title: string; subtitle: string; image: string; link_type: "none" | "category" | "product" | "search"; link_value: string; order: number; active: boolean };
export type BannerInput = Omit<Banner, "banner_id">;
export type HomeSettings = {
  key?: string;
  free_shipping: { enabled: boolean; title: string; subtitle: string; min_purchase: number };
  recommend_mode: "personal" | "random";
};
export type FlashSale = { active: boolean; title?: string; ends_at?: string; items: Product[] };
export type FlashSchedule = { store_id: string; name: string; own: boolean; starts_at: string | null; ends_at: string | null; status: "running" | "upcoming" | "ended" | "off"; follows_sidoarjo: boolean };
export type FlashBranchRow = { store_id: string; name: string; price: number; auto_price: number; flash_price: number };
export type AdminFlashSale = { title: string; active: boolean; ends_at: string; items: { product_id: string; flash_price: number; name: string; image: string; price: number; branches: FlashBranchRow[] }[] };
export type Voucher = {
  code: string; title: string; description: string; mode: DiscountMode; value: number; max_discount: number;
  min_purchase: number; quota: number; used: number; active: boolean; show_on_home: boolean; ends_at: string | null; claimed: boolean;
};
export type VoucherInput = Omit<Voucher, "used" | "claimed">;

export type CustomerType = "langsung" | "pengecer" | "reseller";
export const CUSTOMER_TYPE_LABEL: Record<CustomerType, string> = {
  langsung: "Pembeli Langsung", pengecer: "Pengecer", reseller: "Reseller",
};
export type PriceTier = { min_qty: number; price: number };
export type DiscountMode = "percent" | "rupiah";
export type StoreInfo = {
  name: string; tagline: string; phone: string; whatsapp: string; website: string;
  hours: { day: string; time: string }[];
  branches: { name: string; address: string; phone: string; lat: number; lng: number }[];
};
export type User = {
  user_id: string; email: string; name: string; role: "admin" | "customer" | "store_admin"; customer_type: CustomerType; picture?: string | null;
  email_verified: boolean; phone?: string | null; phone_verified: boolean; gender: string; birthdate: string; has_password: boolean;
};
export type Address = { address_id: string; label: string; recipient: string; phone: string; address: string; city: string; postal_code: string; destination_id?: number | null; destination_label?: string; is_default: boolean };
export type AddressInput = Omit<Address, "address_id">;
export type AppNotification = { notif_id: string; kind: "order" | "promo" | "security" | "product"; title: string; body: string; link: string; read: boolean; created_at: string };
export type ActivityLog = { log_id: string; action: string; detail: string; created_at: string };
export type AccountSettings = { notif_order: boolean; notif_promo: boolean; notif_security: boolean; notif_product: boolean; email_product: boolean };
export type PushStatus = { enabled: boolean; key_ready: boolean; devices: number; updated_at?: string | null;
  last_send?: { at: string; title: string; result: Record<string, number> } | null };
export type ProductUpdates = { digest_id: string; title: string; created_at: string;
  items: { product_id: string; name: string; image: string; kinds: string[]; change: string }[] };
export type HomeSectionKey = "popular" | "newest" | "recommended";
export type HomeSort = "best_selling" | "rating" | "most_viewed" | "newest" | "random" | "personal";
export type HomeSectionCfg = { enabled: boolean; title: string; limit: number; sort: HomeSort; pinned: string[]; categories: string[]; days: number };
export type HomeSectionsInput = Record<HomeSectionKey, HomeSectionCfg>;
export type HomeSectionsSettings = { store_id: string; store_name: string; sections: Record<HomeSectionKey, HomeSectionCfg & { pinned_products: { product_id: string; name: string; image: string; price: number }[] }> };
export type HomeFeed = Record<HomeSectionKey, { enabled: boolean; title: string; limit: number; items: Product[]; more?: boolean }>;
export type Store = { official?: boolean; store_id: string; owner_id: string; name: string; description: string; city: string; phone?: string; logo: string; status: "pending" | "active" | "rejected" | "suspended"; note: string; created_at: string; product_count?: number; owner_name?: string; owner_email?: string; address?: string; pickup_hours?: string };
export type ShopPage = Store & { banner: string; featured: Product[]; featured_manual: boolean };
export type StoreAppearance = { store_id: string; name: string; city: string; banner: string; logo: string; description: string; phone: string; address: string; pickup_hours: string; featured: { product_id: string; name: string; image: string }[] };
export type StoreInput = { name: string; description: string; city: string; phone: string; logo: string; address?: string; pickup_hours?: string };
export type SellerProductInput = { name: string; description: string; category: string; price: number; original_price: number; stock: number; images: string[] };
export type Courier = { code: string; name: string; cost: number; eta: string; active: boolean; source?: "auto" | "manual" };
export type Destination = { id: number; label: string };
export type PaymentSettings = { configured: boolean; key_hint: string; client_key: string; enabled: boolean; production: boolean; key_status?: KeyStatus | null; ready: boolean };
export type KeyStatus = { state: "valid" | "invalid" | "limited" | "unknown"; message: string; checked_at: string };
export type ShippingSettings = { configured: boolean; key_hint: string; enabled: boolean; default_weight_grams: number; origins: Record<string, Destination>; key_status?: KeyStatus | null };
export type InventoryItem = { product_id: string; name: string; image: string; price: number; stock: number; own: boolean };
export type Report = {
  revenue_completed: number; orders_completed: number; revenue_in_progress: number;
  by_status: Record<string, { orders: number; total: number }>;
  daily: { date: string; revenue: number; orders: number }[];
  top_products: { product_id: string; name: string; qty: number; revenue: number }[];
};
export type Category = { category_id: string; name: string; icon: string; image: string; parent?: string | null; count: number };
export type ProductQuery = {
  category?: string; q?: string; sort?: string; skip?: number; limit?: number; store?: string; branch?: string;
  brands?: string[]; min_price?: number | null; max_price?: number | null; in_stock?: boolean; wholesale?: boolean;
};
export type ProductFacets = {
  total: number; price_min: number; price_max: number;
  brands: { name: string; count: number }[]; categories: { category_id: string; name: string; count: number }[];
};
function productQs(p: ProductQuery) {
  const qs = new URLSearchParams();
  for (const k of ["store", "branch", "category", "q", "sort"] as const) if (p[k]) qs.set(k, p[k]!);
  if (p.skip) qs.set("skip", String(p.skip));
  if (p.limit) qs.set("limit", String(p.limit));
  if (p.brands?.length) qs.set("brand", p.brands.join("|"));
  if (p.min_price != null) qs.set("min_price", String(p.min_price));
  if (p.max_price != null) qs.set("max_price", String(p.max_price));
  if (p.in_stock) qs.set("in_stock", "true");
  if (p.wholesale) qs.set("wholesale", "true");
  return qs.toString();
}
export type Product = {
  product_id: string; name: string; category: string; price: number; original_price: number;
  discount: number; rating: number; sold: number; image: string; images: string[]; description: string; stock: number;
  in_stock: boolean; my_price: number; price_tiers: PriceTier[];
  price_min: number; price_max: number;
  price_matrix: ({ min_qty: number } & Record<CustomerType, number>)[];
  flash_price?: number | null; flash_ends_at?: string | null;
  store_id: string; store_name: string;
  brand?: string; condition?: "new" | "used"; video?: string; min_order?: number; max_order?: number;
  variant_options?: VariantOption[]; variants?: (Omit<VariantRow, "active"> & { name: string })[];
  specs?: Partial<Record<SpecKey, string>>; weight_grams?: number; length_cm?: number; width_cm?: number; height_cm?: number;
  preorder?: boolean; preorder_days?: number; processing_days?: number;
};
export type VariantOption = { name: string; values: string[] };
export type VariantRow = { variant_id: string; values: string[]; price: number; stock: number; sku: string; image: string; active: boolean };
export type ProductForm = {
  name: string; category: string; subcategory: string; brand: string; sku: string; barcode: string; condition: "new" | "used"; showcase: string;
  status: "active" | "inactive"; description: string; images: string[]; video: string; price: number; discount_price: number;
  stock: number; min_order: number; max_order: number; low_stock_alert: number;
  variants_enabled: boolean; variant_options: VariantOption[]; variants: VariantRow[];
  specs: Partial<Record<SpecKey, string>>; weight_grams: number; weight_estimated?: boolean; dims_estimated?: boolean; length_cm: number; width_cm: number; height_cm: number;
  couriers: string[]; ship_regular: boolean; ship_cargo: boolean; preorder: boolean; preorder_days: number; processing_days: number;
  seo_title: string; meta_description: string; keywords: string[];
  tier_prices: Partial<Record<CustomerType, PriceTier[]>>;
};
export type SpecKey = "material" | "color" | "size" | "dimensions" | "weight" | "origin_country" | "warranty" | "extra";
export type AccurateSettings = {
  configured: boolean; token_hint: string; secret_hint: string; database_id: string; database_name: string; host: string;
  last_test_at?: string | null; last_test_ok?: boolean | null; last_test_message: string; warehouse_map: Record<string, string>;
  updated_at?: string | null; phase: number; write_enabled: boolean; customer_no: string; shipping_item_no: string; last_sync_at?: string | null;
};
export type AccurateChange = { key: string; product_id: string; name: string; sku: string; field: "price" | "stock"; store_id: string; store_name?: string; warehouse?: string; before: number; after: number };
export type AccurateSyncResult = { price: number; stock: number; new: number; conflict: number };
export type AccuratePreview = {
  preview_id: string; created_at: string; status: string; accurate_total: number; matched: number; truncated: boolean;
  counts: { price: number; stock: number; new: number; skipped: number }; changes: AccurateChange[];
  new_items: { no: string; name: string; price: number; unit: string }[]; skipped: { sku: string; name: string; reason: string }[];
};
export type AccurateInvoiceState = { status: "none" | "sending" | "sent" | "failed"; number?: string; error?: string; at?: string };
export type AccurateOrderRow = { order_id: string; store_name: string; total: number; status: string; created_at: string; payment_method: string; buyer: string; item_count: number; accurate_invoice: AccurateInvoiceState };
export type AccurateInvoice = {
  order_id: string; number: string; customer_no: string; date: string; store_name: string; buyer: string; discount: number; total: number; order_total: number;
  lines: { item_no: string; name: string; quantity: number; unit_price: number; warehouse: string; amount: number }[];
  notes: string[]; problems: string[]; description: string; accurate_invoice: AccurateInvoiceState;
};
export type AccurateItem = { id: number; no: string; name: string; price: number | null; unit: string; stock: number | null; type: string; pgs_product_id: string | null };
export type PriceLog = {
  log_id: string; product_id: string; product_name: string; store_id: string; store_name: string; user_name: string; user_role: string;
  source: string; source_label: string; at: string;
  changes: { field: string; label: string; kind: "price" | "stock"; variant: string; before: number | string | null; after: number | string }[];
};
export type EditorListItem = { product_id: string; name: string; image: string; sku: string; price: number; original_price: number; stock: number; status: "active" | "inactive"; variants: number; sold: number; store_id: string; weight_grams: number; weight_estimated: boolean; dims: number[]; dims_estimated: boolean; shared?: boolean; only_branch?: string };
export type BulkEdit = { store_id?: string | null; product_ids: string[]; price_mode?: "" | "set" | "up_pct" | "down_pct" | "up" | "down"; price_value?: number; stock_mode?: "" | "set" | "add" | "sub"; stock_value?: number; status?: "" | "active" | "inactive"; weight_grams?: number; weight_only_missing?: boolean; dims?: number[]; dims_only_missing?: boolean };
export type EstimateKind = "weight" | "dims";
export type PriceDown = { product_id: string; name: string; old_price: number; new_price: number };
export type BranchBulkPreview = { preview_id: string; store_id: string; changed: number; up: number; down: number; error_count: number; down_sample: PriceDown[];
  errors: { row: number; product_id: string; reason: string }[]; sample: { product_id: string; name: string; before: PriceSet; after: PriceSet }[] };
export type PriceSet = { price: number; original_price: number; tier_prices: Record<string, { min_qty: number; price: number }[]> };
export type BranchPriceItem = { product_id: string; name: string; image: string; sidoarjo: PriceSet; branch: PriceSet; own_price: boolean; stock: number; price_set_at: string | null };
export type BranchPriceList = { store_id: string; store_name: string; items: BranchPriceItem[] };
export type BranchCopyRule = { store_id: string; mode: "rp" | "pct" | "mix"; threshold: number; price_add: number; price_pct: number; stock_sub: number; copy_price: boolean; copy_stock: boolean; overwrite_manual: boolean };
export type BranchCopyPreview = { preview_id: string; branches: { store_id: string; store_name: string; total: number; price_changed: number; stock_changed: number;
  unchanged: number; zero_stock: number; protected: number; protected_overwritten: number; big_rise: number; by_pct: number; by_rp: number; price_down: number; down_sample: PriceDown[];
  protected_sample: { product_id: string; name: string; branch_price: number; would_be: number }[]; sample: { product_id: string; name: string; sidoarjo_price: number; sidoarjo_stock: number; old_price: number; new_price: number; old_stock: number; new_stock: number }[] }[] };
export type NearestStores = { nearest: { store_id: string; name: string; distance_km: number } | null; stores: { store_id: string; name: string; distance_km: number }[] };
export type CategoryPreview = { preview_id: string; total: number; groups: { category_id: string; count: number }[];
  items: { product_id: string; name: string; image: string; suggested: string; confidence: "tinggi" | "sedang" | "rendah"; reason: string }[] };
export type CustomerLocation = { owner: string; guest: boolean; name: string; email: string; phone: string; lat: number; lng: number;
  accuracy: number | null; updated_at: string; first_seen: string; pings: number; orders: number; spent: number; customer_type?: string };
export type CustomerLocations = { stats: { total: number; customers: number; guests: number; active_24h: number; active_7d: number; buyers: number }; items: CustomerLocation[] };
export type FonnteStatus = { has_token: boolean; source: "" | "admin" | "env"; token_hint: string; owner_whatsapp: string; otp_mode: "uji" | "asli";
  updated_at: string | null; last_test: (FonnteTest & { at: string }) | null };
export type FonnteTest = { ok: boolean; reason: string; device: string; device_status: string; name: string; quota: string; expired: string; package: string };
export type WeightPreview = { preview_id: string; total: number; items: { product_id: string; name: string; image: string; grams?: number; dims?: number[]; rule: string }[]; groups: { rule: string; count: number }[] };
export type ImportRow = { row: number; name: string; action: "update" | "same" | "create" | "draft" | "skip"; message: string };
export type ImportReport = { committed: boolean; counts: Record<ImportRow["action"], number>; rows: ImportRow[]; format: "xlsx" | "csv";
  columns: { sheet: string; header: string; field: string | null; label: string }[]; missing: string[] };
export type ProductDraft = { draft_id: string; product_id?: string | null; store_id: string; data: ProductForm; updated_at: string };
export type EditorContext = {
  admin: boolean; stores: { store_id: string; name: string }[]; showcases: string[];
  shipping: Record<string, { origin: string; pickup: boolean; couriers: { code: string; name: string; cargo: boolean }[] }>;
  limits: { images: number; image_mb: number; video_mb: number; combos: number };
};
export type CartItem = { key: string; variant_id?: string | null; variant_name?: string; min_order?: number; max_order?: number; product_id: string; quantity: number; name: string; price: number; base_price: number; original_price: number; image: string; stock: number; next_tier?: PriceTier | null; store_id: string; store_name: string };
export type Cart = { items: CartItem[]; subtotal: number; savings: number; item_count: number; customer_type: CustomerType };
export type PaymentMethod = "midtrans" | "xendit" | "cod" | "saldo";
export type CheckoutPayload = { full_name: string; phone: string; address: string; city: string; payment_method: PaymentMethod; use_balance?: boolean; voucher_code?: string; store_id: string; courier: string; destination_id?: number | null; expected_shipping_cost?: number; destination_label?: string };
export type OrderItem = { product_id: string; name: string; price: number; quantity: number; image: string; variant_id?: string | null; variant_name?: string };
export type Order = {
  order_id: string; user_id?: string | null; items: OrderItem[]; subtotal: number; shipping_cost: number; discount?: number; voucher_code?: string | null; total: number;
  shipping: Record<string, string>; status: "pending" | "paid" | "expired" | "failed" | "cod" | "processing" | "shipped" | "completed" | "cancelled"; payment_method: PaymentMethod;
  payment_url?: string | null; customer_type: CustomerType; created_at: string;
  store_id: string; store_name: string; courier?: { code: string; name: string; cost: number; eta: string } | null;
  tracking_number: string; status_history: { status: Order["status"]; at: string; note: string }[];
  balance_used?: number; refunded?: number; complaint_id?: string | null;
  expires_at?: string | null; ready_at?: string | null; pickup_code?: string | null;
};
export type AdminStats = { orders_today: number; revenue_today: number; need_action: number; waiting_payment: number; customers: number; products: number };
export const ORDER_STATUS_LABEL: Record<Order["status"], string> = {
  pending: "Menunggu Pembayaran", paid: "Dibayar", expired: "Kedaluwarsa", failed: "Gagal", cod: "Bayar di Tempat",
  processing: "Diproses", shipped: "Dikirim", completed: "Selesai", cancelled: "Dibatalkan",
};
export type BranchRow = { store_id: string; name: string; city: string; address?: string; pickup_hours?: string; phone?: string; stock: Record<string, number>; available: boolean; distance_km: number | null };
export type BranchSuggest = { located: boolean; suggested: string | null; stores: BranchRow[] };
