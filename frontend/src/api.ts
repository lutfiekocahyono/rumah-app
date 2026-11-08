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

async function headers(): Promise<Record<string, string>> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const token = await getToken();
  if (token) h["Authorization"] = `Bearer ${token}`;
  h["X-Guest-Id"] = await getGuestId();
  h["X-Store-Id"] = currentStore;
  return h;
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = `${BASE}/api${path}`;
  const res = await fetch(url, { ...init, headers: { ...(await headers()), ...(init.headers || {}) } });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      const d = data.detail;
      msg = Array.isArray(d) ? d.map((x: any) => x?.msg).filter(Boolean).join(", ") || msg : (typeof d === "string" ? d : data.message || msg);
    } catch {}
    throw Object.assign(new Error(msg), { status: res.status });
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
  products: (params: { category?: string; q?: string; sort?: string; skip?: number; limit?: number; store?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.store) qs.set("store", params.store);
    if (params.category) qs.set("category", params.category);
    if (params.q) qs.set("q", params.q);
    if (params.sort) qs.set("sort", params.sort);
    if (params.skip) qs.set("skip", String(params.skip));
    if (params.limit) qs.set("limit", String(params.limit));
    const s = qs.toString();
    return req<Product[]>(`/products${s ? "?" + s : ""}`);
  },
  product: (id: string) => req<Product>(`/products/${id}`),

  // cart
  getCart: () => req<Cart>("/cart"),
  addCart: (product_id: string, quantity = 1) =>
    req<Cart>("/cart/items", { method: "POST", body: JSON.stringify({ product_id, quantity }) }),
  updateCart: (product_id: string, quantity: number) =>
    req<Cart>(`/cart/items/${product_id}`, { method: "PUT", body: JSON.stringify({ product_id, quantity }) }),
  removeCart: (product_id: string) => req<Cart>(`/cart/items/${product_id}`, { method: "DELETE" }),
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
  adminPricing: () => req<Pricing>("/admin/pricing"),
  adminSavePricing: (p: Pricing) => req<Pricing>("/admin/pricing", { method: "PUT", body: JSON.stringify(p) }),
  adminCustomers: (q = "") => req<User[]>(`/admin/customers${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  adminSetCustomerType: (user_id: string, customer_type: CustomerType) =>
    req<User>(`/admin/customers/${user_id}`, { method: "PUT", body: JSON.stringify({ customer_type }) }),
  adminProductTiers: (id: string) => req<ProductTiers>(`/admin/products/${id}/tiers`),
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
  adminSaveProductTiers: (id: string, tier_prices: ProductTiers["tier_prices"]) =>
    req<ProductTiers>(`/admin/products/${id}/tiers`, { method: "PUT", body: JSON.stringify({ tier_prices }) }),

  // homepage promo
  banners: () => req<Banner[]>("/banners"),
  homeSettings: () => req<HomeSettings>("/home-settings"),
  flashSale: () => req<FlashSale>("/flash-sale"),
  vouchers: () => req<Voucher[]>("/vouchers"),
  myVouchers: () => req<Voucher[]>("/vouchers/mine"),
  claimVoucher: (code: string) => req<Voucher>(`/vouchers/${encodeURIComponent(code)}/claim`, { method: "POST" }),
  applyVoucher: (code: string) => req<{ code: string; title: string; discount: number }>("/vouchers/apply", { method: "POST", body: JSON.stringify({ code }) }),
  trackView: (product_id: string) => req<{ ok: boolean }>(`/activity/view/${product_id}`, { method: "POST" }),
  recommendations: (skip = 0, limit = 20) => req<Product[]>(`/recommendations?skip=${skip}&limit=${limit}`),

  // admin promo
  adminBanners: () => req<Banner[]>("/admin/banners"),
  adminSaveBanner: (b: BannerInput, id?: string) =>
    req<Banner>(id ? `/admin/banners/${id}` : "/admin/banners", { method: id ? "PUT" : "POST", body: JSON.stringify(b) }),
  adminDeleteBanner: (id: string) => req<{ ok: boolean }>(`/admin/banners/${id}`, { method: "DELETE" }),
  adminFlashSale: () => req<AdminFlashSale>("/admin/flash-sale"),
  adminSaveFlashSale: (f: { title: string; active: boolean; ends_at: string; items: { product_id: string; flash_price: number }[] }) =>
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
  unreadCount: () => req<{ count: number }>("/notifications/unread-count"),
  readAll: () => req<{ ok: boolean }>("/notifications/read-all", { method: "POST" }),
  readOne: (id: string) => req<{ ok: boolean }>(`/notifications/${id}/read`, { method: "POST" }),

  // seller
  myStore: () => req<Store | null>("/me/store"),
  openStore: (s: StoreInput) => req<Store>("/stores", { method: "POST", body: JSON.stringify(s) }),
  editStore: (s: StoreInput) => req<Store>("/me/store", { method: "PUT", body: JSON.stringify(s) }),
  storePage: (id: string) => req<Store>(`/stores/${id}`),
  sellerProducts: () => req<Product[]>("/seller/products"),
  sellerSaveProduct: (p: SellerProductInput, id?: string) =>
    req<Product>(id ? `/seller/products/${id}` : "/seller/products", { method: id ? "PUT" : "POST", body: JSON.stringify(p) }),
  sellerDeleteProduct: (id: string) => req<{ ok: boolean }>(`/seller/products/${id}`, { method: "DELETE" }),
  sellerUpload: (file: LocalFile) => uploadTo("/seller/upload", file),
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
  sellerReport: () => req<Report>("/seller/report"),
  adminReport: () => req<{ all: Report; stores: (Report & { store_id: string; name: string })[] }>("/admin/report"),
  shippingSettings: () => req<ShippingSettings>("/admin/shipping-settings"),
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
  startChat: (store_id: string) => req<Conversation>("/chats", { method: "POST", body: JSON.stringify({ store_id }) }),
  sellerStartChat: (order_id: string) => req<Conversation>("/seller/chats", { method: "POST", body: JSON.stringify({ order_id }) }),
  chats: (side: "buyer" | "store") => req<Conversation[]>(side === "store" ? "/seller/chats" : "/chats"),
  chatUnread: () => req<{ buyer: number; store: number }>("/chats/unread"),
  chatThread: (id: string, after?: string) => req<ChatThread>(`/chats/${id}${after ? `?after=${encodeURIComponent(after)}` : ""}`),
  sendChat: (id: string, text: string) => req<ChatMessage>(`/chats/${id}/messages`, { method: "POST", body: JSON.stringify({ text }) }),
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
export type ChatMessage = { msg_id: string; conv_id: string; sender: "user" | "store"; text: string; created_at: string };
export type ChatThread = { conversation: Conversation; me: "user" | "store"; messages: ChatMessage[] };

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
export type AdminFlashSale = { title: string; active: boolean; ends_at: string; items: { product_id: string; flash_price: number; name: string; image: string; price: number }[] };
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
export type Pricing = {
  type_discounts: Record<CustomerType, number>;
  type_discount_modes: Record<CustomerType, DiscountMode>;
  qty_tiers: { min_qty: number; mode: DiscountMode; value: number; discount_percent?: number }[];
};
export type ProductTiers = { product_id: string; name: string; price: number; image: string; tier_prices: Record<CustomerType, PriceTier[]> };
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
export type AppNotification = { notif_id: string; kind: "order" | "promo" | "security"; title: string; body: string; link: string; read: boolean; created_at: string };
export type ActivityLog = { log_id: string; action: string; detail: string; created_at: string };
export type AccountSettings = { notif_order: boolean; notif_promo: boolean; notif_security: boolean };
export type Store = { official?: boolean; store_id: string; owner_id: string; name: string; description: string; city: string; phone?: string; logo: string; status: "pending" | "active" | "rejected" | "suspended"; note: string; created_at: string; product_count?: number; owner_name?: string; owner_email?: string };
export type StoreInput = { name: string; description: string; city: string; phone: string; logo: string };
export type SellerProductInput = { name: string; description: string; category: string; price: number; original_price: number; stock: number; images: string[] };
export type Courier = { code: string; name: string; cost: number; eta: string; active: boolean; source?: "auto" | "manual" };
export type Destination = { id: number; label: string };
export type ShippingSettings = { configured: boolean; key_hint: string; enabled: boolean; default_weight_grams: number; origins: Record<string, Destination> };
export type InventoryItem = { product_id: string; name: string; image: string; price: number; stock: number; own: boolean };
export type Report = {
  revenue_completed: number; orders_completed: number; revenue_in_progress: number;
  by_status: Record<string, { orders: number; total: number }>;
  daily: { date: string; revenue: number; orders: number }[];
  top_products: { product_id: string; name: string; qty: number; revenue: number }[];
};
export type Category = { category_id: string; name: string; icon: string; image: string; parent?: string | null; count: number };
export type Product = {
  product_id: string; name: string; category: string; price: number; original_price: number;
  discount: number; rating: number; sold: number; image: string; images: string[]; description: string; stock: number;
  in_stock: boolean; my_price: number; price_tiers: PriceTier[];
  price_min: number; price_max: number;
  price_matrix: ({ min_qty: number } & Record<CustomerType, number>)[];
  flash_price?: number | null; flash_ends_at?: string | null;
  store_id: string; store_name: string;
};
export type CartItem = { product_id: string; quantity: number; name: string; price: number; base_price: number; original_price: number; image: string; stock: number; next_tier?: PriceTier | null; store_id: string; store_name: string };
export type Cart = { items: CartItem[]; subtotal: number; savings: number; item_count: number; customer_type: CustomerType };
export type PaymentMethod = "midtrans" | "xendit" | "cod" | "saldo";
export type CheckoutPayload = { full_name: string; phone: string; address: string; city: string; payment_method: PaymentMethod; use_balance?: boolean; voucher_code?: string; store_id: string; courier: string; destination_id?: number | null; expected_shipping_cost?: number; destination_label?: string };
export type OrderItem = { product_id: string; name: string; price: number; quantity: number; image: string };
export type Order = {
  order_id: string; user_id?: string | null; items: OrderItem[]; subtotal: number; shipping_cost: number; discount?: number; voucher_code?: string | null; total: number;
  shipping: Record<string, string>; status: "pending" | "paid" | "expired" | "failed" | "cod" | "processing" | "shipped" | "completed" | "cancelled"; payment_method: PaymentMethod;
  payment_url?: string | null; customer_type: CustomerType; created_at: string;
  store_id: string; store_name: string; courier?: { code: string; name: string; cost: number; eta: string } | null;
  tracking_number: string; status_history: { status: Order["status"]; at: string; note: string }[];
  balance_used?: number; refunded?: number; complaint_id?: string | null;
};
export type AdminStats = { orders_today: number; revenue_today: number; need_action: number; waiting_payment: number; customers: number; products: number };
export const ORDER_STATUS_LABEL: Record<Order["status"], string> = {
  pending: "Menunggu Pembayaran", paid: "Dibayar", expired: "Kedaluwarsa", failed: "Gagal", cod: "Bayar di Tempat",
  processing: "Diproses", shipped: "Dikirim", completed: "Selesai", cancelled: "Dibatalkan",
};
