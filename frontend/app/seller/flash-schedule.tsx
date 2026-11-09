import React from "react";
import { ScrollView, Text } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { spacing } from "@/src/theme";
import { SellerShell } from "@/src/components/seller-shell";
import { FlashScheduleList } from "@/src/components/flash-schedule";
import { adminStyles } from "@/src/components/admin-form";

/** Admin cabang: atur jam mulai & selesai Flash Sale untuk tokonya sendiri. */
export default function SellerFlashSchedule() {
  const insets = useSafeAreaInsets();
  return (
    <SellerShell admin={false} title="Jadwal Flash Sale">
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled" testID="seller-flash-schedule-screen">
        <Text style={adminStyles.muted}>Produk & harga Flash Sale diatur Super Admin. Di sini Anda mengatur kapan Flash Sale mulai dan selesai untuk pembeli cabang Anda.</Text>
        <FlashScheduleList />
      </ScrollView>
    </SellerShell>
  );
}
