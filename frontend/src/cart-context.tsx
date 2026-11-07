import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, type Cart, type Product } from "./api";
import { useAuth } from "./auth-context";

type CartCtx = {
  cart: Cart;
  wishlist: Product[];
  loading: boolean;
  refresh: () => Promise<void>;
  addToCart: (product_id: string, quantity?: number) => Promise<void>;
  updateQty: (product_id: string, quantity: number) => Promise<void>;
  removeItem: (product_id: string) => Promise<void>;
  clear: () => Promise<void>;
  toggleWishlist: (product_id: string) => Promise<void>;
  isWished: (product_id: string) => boolean;
};

const empty: Cart = { items: [], subtotal: 0, item_count: 0 };
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

  // Errors are swallowed here so a network failure never crashes a screen.
  const safe = async (fn: () => Promise<void>) => {
    try { await fn(); } catch (e) { console.warn("cart error", e); }
  };
  const addToCart = (product_id: string, quantity = 1) =>
    safe(async () => setCart(await api.addCart(product_id, quantity)));
  const updateQty = (product_id: string, quantity: number) =>
    safe(async () => setCart(await api.updateCart(product_id, quantity)));
  const removeItem = (product_id: string) =>
    safe(async () => setCart(await api.removeCart(product_id)));
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
