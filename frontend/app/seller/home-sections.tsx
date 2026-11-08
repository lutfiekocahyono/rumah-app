import React from "react";
import { View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { adminStyles } from "@/src/components/admin-form";
import { ScreenHeader } from "@/src/components/screen-header";
import { HomeSectionsEditor } from "@/src/components/home-sections-editor";

export default function SellerHomeSections() {
  const insets = useSafeAreaInsets();
  return (
    <View style={[adminStyles.root, { paddingTop: insets.top }]} testID="seller-home-sections-screen">
      <ScreenHeader title="Produk di Beranda" />
      <HomeSectionsEditor load={api.sellerHomeSections} save={api.saveSellerHomeSections} />
    </View>
  );
}
