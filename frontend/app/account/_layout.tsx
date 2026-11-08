import React from "react";
import { View, ActivityIndicator } from "react-native";
import { Redirect, Stack } from "expo-router";

import { colors } from "@/src/theme";
import { useAuth } from "@/src/auth-context";

/** All /account/* screens need a signed-in user; guests are sent to login. */
export default function AccountLayout() {
  const { user, loading } = useAuth();
  if (loading) {
    return <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}><ActivityIndicator color={colors.brandPrimary} /></View>;
  }
  if (!user) return <Redirect href={"/login" as any} />;
  return <Stack screenOptions={{ headerShown: false }} />;
}
