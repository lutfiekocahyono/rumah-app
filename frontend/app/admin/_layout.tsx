import React from "react";
import { View, ActivityIndicator } from "react-native";
import { Redirect, Stack } from "expo-router";

import { colors } from "@/src/theme";
import { useAuth } from "@/src/auth-context";

/** Admin panel & cross-store reports are for the owner (super admin) only. */
export default function AdminLayout() {
  const { user, loading } = useAuth();
  if (loading) {
    return <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}><ActivityIndicator color={colors.brandPrimary} /></View>;
  }
  if (user?.role !== "admin") return <Redirect href={(user ? "/(tabs)/akun" : "/login") as any} />;
  return <Stack screenOptions={{ headerShown: false }} />;
}
