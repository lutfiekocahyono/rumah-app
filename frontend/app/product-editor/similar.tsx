import React from "react";
import { ScrollView, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { spacing } from "@/src/theme";
import { useAuth } from "@/src/auth-context";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles } from "@/src/components/admin-form";
import { SimilarSection } from "@/src/components/product-editor/similar-section";

/** Produk Serupa untuk produk katalog bersama (admin cabang tidak membuka Ubah Produk untuk produk Sidoarjo). */
export default function SimilarEditor() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const { product } = useLocalSearchParams<{ product: string }>();
  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="similar-editor-screen">
      <ScreenHeader title="Produk Serupa" />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl }} keyboardShouldPersistTaps="handled">
        <SimilarSection productId={product ?? null} admin={user?.role === "admin"} />
      </ScrollView>
    </View>
  );
}
