import { Tabs } from "expo-router";

/** Tab screens; the bottom navigation bar itself is drawn by AppChrome on every page. */
export default function TabsLayout() {
  return (
    <Tabs tabBar={() => null} screenOptions={{ headerShown: false }}>
      <Tabs.Screen name="index" options={{ title: "Beranda" }} />
      <Tabs.Screen name="katalog" options={{ title: "Katalog Produk" }} />
      <Tabs.Screen name="kategori" options={{ title: "Kategori" }} />
      <Tabs.Screen name="keranjang" options={{ title: "Keranjang" }} />
      <Tabs.Screen name="akun" options={{ title: "Akun" }} />
    </Tabs>
  );
}
