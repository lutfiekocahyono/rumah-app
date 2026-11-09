import React from "react";
import { View } from "react-native";
import { WebView } from "react-native-webview";

import { colors } from "@/src/theme";
import { mapHtml, type MapPoint } from "@/src/utils/map-html";

export function CustomerMap({ points, height }: { points: MapPoint[]; height: number }) {
  return (
    <View style={{ height, borderRadius: 12, overflow: "hidden", backgroundColor: colors.surfaceTertiary }} testID="customer-map">
      <WebView originWhitelist={["*"]} source={{ html: mapHtml(points, { buyer: colors.success, customer: colors.brandPrimary, guest: colors.muted }) }} />
    </View>
  );
}
