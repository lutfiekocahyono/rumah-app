import React from "react";
import { View } from "react-native";

import { colors } from "@/src/theme";
import { mapHtml, type MapPoint } from "@/src/utils/map-html";

/** Web: WebView is not available, the same Leaflet page runs in an iframe. */
export function CustomerMap({ points, height }: { points: MapPoint[]; height: number }) {
  const html = mapHtml(points, { buyer: colors.success, customer: colors.brandPrimary, guest: colors.muted });
  return (
    <View style={{ height, borderRadius: 12, overflow: "hidden", backgroundColor: colors.surfaceTertiary }} testID="customer-map">
      {React.createElement("iframe", { srcDoc: html, title: "Peta pelanggan", style: { border: 0, width: "100%", height: "100%" } })}
    </View>
  );
}
