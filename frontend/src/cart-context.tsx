import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, type Cart, type Product } from "./api";
import { useAuth } from "./auth-context";

type CartCtx = {
  cart: Cart;
  wishlist: Product[];
  loading: boolean;
  refresh: () => Promise<void>;
  addToCart: (product_id: string, quantity?: number, variant_id?: string | null) => Promise<string | null>;
  updateQty: (key: string, quantity: number) => Promise<string | null>;
  removeItem: (key: string) => Promise<string | null>;
  clear: () => Promise<string | null>;
  toggleWishlist: (product_id: string) => Promise<string | null>;
  isWished: (product_id: string) => boolean;
};

const empty: Cart = { items: [], subtotal: 0, savings: 0, item_count: 0, customer_type: "langsung" };
const Ctx = createContext<CartCtx | null>(null);

export function CartProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [cart, setCart] = useState<Cart>(empty);
  const [wishlist, setWishlist] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [c, w] = await Promise.all([api.getCart(), api.getWishlist()]);
      setCart(c);
      setWishlist(w.items);
    } catch (e) {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh, user?.user_id]);

  // Errors are caught here so a network failure never crashes a screen; the message is returned.
  const safe = async (fn: () => Promise<void>): Promise<string | null> => {
    try { await fn(); return null; } catch (e: any) { return e?.message || "Terjadi kesalahan"; }
  };
  const addToCart = (product_id: string, quantity = 1, variant_id?: string | null) =>
    safe(async () => setCart(await api.addCart(product_id, quantity, variant_id)));  const updateQty = (key: string, quantity: number) =>
    safe(async () => setCart(await api.updateCart(key, quantity)));
  const removeItem = (key: string) =>
    safe(async () => setCart(await api.removeCart(key)));
  const clear = () => safe(async () => setCart(await api.clearCart()));
  const toggleWishlist = (product_id: string) =>
    safe(async () => {
      const wished = wishlist.some((p) => p.product_id === product_id);
      const w = wished ? await api.removeWishlist(product_id) : await api.addWishlist(product_id);
      setWishlist(w.items);
    });
  const isWished = (product_id: string) => wishlist.some((p) => p.product_id === product_id);

  return (
    <Ctx.Provider value={{ cart, wishlist, loading, refresh, addToCart, updateQty, removeItem, clear, toggleWishlist, isWished }}>
      {children}
    </Ctx.Provider>
  );
}

export function useCart(): CartCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useCart outside CartProvider");
  return v;
}
