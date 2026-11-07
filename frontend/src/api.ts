import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

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

async function headers(): Promise<Record<string, string>> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const token = await getToken();
  if (token) h["Authorization"] = `Bearer ${token}`;
  h["X-Guest-Id"] = await getGuestId();
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
    throw new Error(msg);
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

  // catalog
  categories: () => req<Category[]>("/categories"),
  products: (params: { category?: string; q?: string; sort?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.category) qs.set("category", params.category);
    if (params.q) qs.set("q", params.q);
    if (params.sort) qs.set("sort", params.sort);
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
};

export type User = { user_id: string; email: string; name: string };
export type Category = { category_id: string; name: string; icon: string; image: string };
export type Product = {
  product_id: string; name: string; category: string; price: number; original_price: number;
  discount: number; rating: number; sold: number; image: string; images: string[]; description: string; stock: number;
};
export type CartItem = { product_id: string; quantity: number; name: string; price: number; original_price: number; image: string; stock: number };
export type Cart = { items: CartItem[]; subtotal: number; item_count: number };
export type CheckoutPayload = { full_name: string; phone: string; address: string; city: string; payment_method?: string };
export type OrderItem = { product_id: string; name: string; price: number; quantity: number; image: string };
export type Order = { order_id: string; user_id?: string | null; items: OrderItem[]; total: number; shipping: Record<string, string>; status: string; created_at: string };
