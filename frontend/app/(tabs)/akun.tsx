import React from "react";
import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { useAuth } from "@/src/auth-context";
import { CUSTOMER_TYPE_LABEL } from "@/src/api";
import { Image } from "expo-image";
import { GoogleButton } from "@/src/components/google-button";

type MenuItem = { icon: string; label: string; to?: string; onPress?: () => void; danger?: boolean };

export default function Akun() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, logout } = useAuth();

  const menuGroups: { title: string; items: MenuItem[] }[] = [
    ...(user?.role === "admin"
      ? [{
          title: "Admin",
          items: [
            { icon: "speedometer-outline", label: "Admin Panel", to: "/admin" },
            { icon: "receipt-outline", label: "Pesanan Masuk", to: "/admin/orders" },
            { icon: "pricetags-outline", label: "Pengaturan Harga", to: "/admin/pricing" },
            { icon: "people-outline", label: "Kategori Pelanggan", to: "/admin/customers" },
            { icon: "cube-outline", label: "Harga Manual per Produk", to: "/admin/products" },
          ],
        }]
      : []),
    {
      title: "Pesanan",
      items: [
        { icon: "receipt-outline", label: "Daftar Pesanan", to: "/orders" },
        { icon: "heart-outline", label: "Wishlist", to: "/wishlist" },
      ],
    },
    {
      title: "Toko",
      items: [
        { icon: "storefront-outline", label: "Alamat & Kontak Toko", to: "/store" },
      ],
    },
  ];

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="akun-screen">
      <View style={styles.header}>
        <Text style={styles.title}>Akun</Text>
      </View>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: spacing["2xl"] }}>
        {user ? (
          <View style={styles.profile} testID="profile-card">
            <View style={styles.avatar}>
              {user.picture ? (
                <Image source={user.picture} style={styles.avatarImg} />
              ) : (
                <Text style={styles.avatarText}>{user.name?.[0]?.toUpperCase() ?? "U"}</Text>
              )}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.name}>{user.name}</Text>
              <Text style={styles.email}>{user.email}</Text>
              <View style={styles.badgeRow}>
                <View style={styles.typeBadge} testID="customer-type-badge">
                  <Text style={styles.typeBadgeText}>{CUSTOMER_TYPE_LABEL[user.customer_type]}</Text>
                </View>
                {user.role === "admin" ? (
                  <View style={[styles.typeBadge, { backgroundColor: colors.surfaceInverse }]}>
                    <Text style={[styles.typeBadgeText, { color: colors.onSurfaceInverse }]}>Admin</Text>
                  </View>
                ) : null}
              </View>
            </View>
          </View>
        ) : (
          <View style={styles.guestCard} testID="guest-card">
            <Text style={styles.guestTitle}>Belum masuk</Text>
            <Text style={styles.guestText}>Login untuk menyimpan alamat, melihat pesanan, dan belanja lebih nyaman.</Text>
            <View style={styles.guestBtns}>
              <Pressable testID="login-nav-btn" style={styles.primaryBtn} onPress={() => router.push("/login" as any)}>
                <Text style={styles.primaryBtnText}>Masuk</Text>
              </Pressable>
              <Pressable testID="register-nav-btn" style={styles.outlineBtn} onPress={() => router.push("/register" as any)}>
                <Text style={styles.outlineBtnText}>Daftar</Text>
              </Pressable>
            </View>
            <GoogleButton testID="akun-google-btn" label="Daftar / Masuk dengan Google" />
          </View>
        )}

        {menuGroups.map((g) => (
          <View key={g.title} style={styles.group}>
            <Text style={styles.groupTitle}>{g.title}</Text>
            <View style={styles.list}>
              {g.items.map((m, i) => (
                <Pressable
                  key={m.label}
                  testID={`menu-${m.label.toLowerCase().replace(/\s+/g, "-")}`}
                  style={[styles.row, i === g.items.length - 1 && { borderBottomWidth: 0 }]}
                  onPress={() => (m.to ? router.push(m.to as any) : m.onPress?.())}
                >
                  <Icon name={m.icon as any} size={20} color={colors.onSurface} />
                  <Text style={styles.rowLabel}>{m.label}</Text>
                  <Icon name="chevron-forward" size={18} color={colors.muted} />
                </Pressable>
              ))}
            </View>
          </View>
        ))}

        {user ? (
          <Pressable testID="logout-btn" style={styles.logout} onPress={logout}>
            <Icon name="log-out-outline" size={20} color={colors.error} />
            <Text style={styles.logoutText}>Keluar</Text>
          </Pressable>
        ) : null}

        <Text style={styles.footer}>Pusat Grosir Sidoarjo · v1.0.0</Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  title: { fontSize: fontSize.xl, fontWeight: "500", color: colors.onSurface },

  profile: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg },
  avatar: { width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  avatarText: { color: colors.onBrandPrimary, fontSize: fontSize.xl, fontWeight: "500" },
  avatarImg: { width: 56, height: 56, borderRadius: 28 },
  badgeRow: { flexDirection: "row", gap: 6, marginTop: 6 },
  typeBadge: { backgroundColor: colors.brandTertiary, paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.sm },
  typeBadgeText: { color: colors.onBrandTertiary, fontSize: 11, fontWeight: "500" },
  name: { fontSize: fontSize.lg, color: colors.onSurface, fontWeight: "500" },
  email: { fontSize: fontSize.sm, color: colors.muted, marginTop: 2 },

  guestCard: {
    margin: spacing.lg, padding: spacing.lg, backgroundColor: colors.brandTertiary,
    borderRadius: radius.md, gap: spacing.sm,
  },
  guestTitle: { fontSize: fontSize.lg, color: colors.onSurface, fontWeight: "500" },
  guestText: { fontSize: fontSize.sm, color: colors.onSurface, opacity: 0.8 },
  guestBtns: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  primaryBtn: { flex: 1, backgroundColor: colors.brandPrimary, paddingVertical: 10, borderRadius: radius.pill, alignItems: "center" },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "500" },
  outlineBtn: { flex: 1, borderWidth: 1, borderColor: colors.brandPrimary, paddingVertical: 10, borderRadius: radius.pill, alignItems: "center" },
  outlineBtnText: { color: colors.brandPrimary, fontWeight: "500" },

  group: { marginTop: spacing.md, paddingHorizontal: spacing.lg },
  groupTitle: { fontSize: fontSize.sm, color: colors.muted, marginBottom: spacing.sm },
  list: { backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  row: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    paddingHorizontal: spacing.md, paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.divider,
  },
  rowLabel: { flex: 1, fontSize: fontSize.base, color: colors.onSurface },

  logout: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    marginHorizontal: spacing.lg, marginTop: spacing.xl,
    paddingVertical: spacing.md,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.error,
  },
  logoutText: { color: colors.error, fontWeight: "500" },

  footer: { textAlign: "center", color: colors.muted, fontSize: 11, marginTop: spacing.xl },
});
