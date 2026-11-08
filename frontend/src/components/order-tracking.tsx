import React from "react";
import { View, Text, StyleSheet } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { ORDER_STATUS_LABEL, type Order } from "@/src/api";
import { fmtDate } from "@/src/utils/date";

/** Store, courier, tracking number and status timeline of an order. */
export function OrderTracking({ order }: { order: Order }) {
  const history = [...(order.status_history ?? [])].reverse();
  return (
    <View style={styles.card} testID="order-tracking">
      <View style={styles.row}>
        <Icon name="storefront-outline" size={18} color={colors.brandPrimary} />
        <Text style={styles.strong}>{order.store_name}</Text>
      </View>
      {order.courier ? (
        <View style={styles.row}>
          <Icon name="car-outline" size={18} color={colors.brandPrimary} />
          <Text style={styles.text}>{order.courier.name} · {order.courier.cost ? formatIDR(order.courier.cost) : "Gratis"}{order.courier.eta ? ` · ${order.courier.eta}` : ""}</Text>
        </View>
      ) : null}
      <View style={styles.row}>
        <Icon name="barcode-outline" size={18} color={colors.brandPrimary} />
        <Text style={styles.text} testID="order-resi">No. resi: {order.tracking_number || "belum ada"}</Text>
      </View>
      {history.length ? (
        <View style={styles.timeline}>
          {history.map((h, i) => (
            <View key={`${h.status}-${h.at}`} style={styles.step}>
              <View style={[styles.dot, i === 0 && { backgroundColor: colors.brandPrimary }]} />
              <View style={{ flex: 1 }}>
                <Text style={[styles.text, i === 0 && styles.strong]}>{ORDER_STATUS_LABEL[h.status] ?? h.status}{h.note ? ` — ${h.note}` : ""}</Text>
                <Text style={styles.muted}>{fmtDate(h.at)}</Text>
              </View>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  strong: { fontSize: fontSize.sm, fontWeight: "600", color: colors.onSurface },
  text: { fontSize: fontSize.sm, color: colors.onSurface, flexShrink: 1 },
  muted: { fontSize: 11, color: colors.muted },
  timeline: { marginTop: spacing.sm, gap: spacing.md, borderLeftWidth: 2, borderLeftColor: colors.border, marginLeft: 6, paddingLeft: spacing.md },
  step: { flexDirection: "row", gap: spacing.sm },
  dot: { position: "absolute", left: -spacing.md - 7, top: 4, width: 12, height: 12, borderRadius: 6, backgroundColor: colors.border },
});
