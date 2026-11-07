import { Tabs } from "expo-router";
import Icon from "@react-native-vector-icons/ionicons";
import { View, Text, StyleSheet, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fontSize } from "@/src/theme";
import { useCart } from "@/src/cart-context";

function TabBarIcon({ name, focused }: { name: string; focused: boolean }) {
  return (
    <Icon name={name as any} size={24} color={focused ? colors.brandPrimary : colors.muted} />
  );
}

function CartTabIcon({ focused }: { focused: boolean }) {
  const { cart } = useCart();
  return (
    <View>
      <Icon name="cart-outline" size={24} color={focused ? colors.brandPrimary : colors.muted} />
      {cart.item_count > 0 ? (
        <View style={styles.badge} testID="cart-tab-badge">
          <Text style={styles.badgeText}>{cart.item_count > 99 ? "99+" : cart.item_count}</Text>
        </View>
      ) : null}
    </View>
  );
}

export default function TabsLayout() {
  const insets = useSafeAreaInsets();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: StyleSheet.hairlineWidth,
          ...(Platform.OS === "web" ? { height: 64 + insets.bottom } : {}),
        },
        tabBarItemStyle: { alignSelf: "center" },
        tabBarLabelStyle: { fontSize: 11 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Home",
          tabBarIcon: ({ focused }) => <TabBarIcon name={focused ? "home" : "home-outline"} focused={focused} />,
          tabBarButtonTestID: "tab-home",
        }}
      />
      <Tabs.Screen
        name="kategori"
        options={{
          title: "Kategori",
          tabBarIcon: ({ focused }) => <TabBarIcon name={focused ? "grid" : "grid-outline"} focused={focused} />,
          tabBarButtonTestID: "tab-kategori",
        }}
      />
      <Tabs.Screen
        name="keranjang"
        options={{
          title: "Keranjang",
          tabBarIcon: ({ focused }) => <CartTabIcon focused={focused} />,
          tabBarButtonTestID: "tab-keranjang",
        }}
      />
      <Tabs.Screen
        name="akun"
        options={{
          title: "Akun",
          tabBarIcon: ({ focused }) => <TabBarIcon name={focused ? "person" : "person-outline"} focused={focused} />,
          tabBarButtonTestID: "tab-akun",
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  badge: {
    position: "absolute",
    top: -4,
    right: -8,
    minWidth: 16,
    height: 16,
    paddingHorizontal: 4,
    borderRadius: 8,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  badgeText: { color: colors.onBrandPrimary, fontSize: 10, fontWeight: "500" },
});
