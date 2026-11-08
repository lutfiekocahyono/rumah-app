import React from "react";
import { View, Text, Pressable } from "react-native";
import Icon from "@react-native-vector-icons/ionicons";
import { colors, fontSize, spacing, formatIDR } from "@/src/theme";
import type { Courier } from "@/src/api";
import { co } from "./styles";

export function CourierList({ couriers, selected, onPick }: { couriers: Courier[]; selected: string; onPick: (code: string) => void }) {
  return (
    <>
      {couriers.map((c) => (
        <Pressable key={c.code} testID={`co-courier-${c.code}`} onPress={() => onPick(c.code)}
          style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 48 }}>
          <Icon name={selected === c.code ? "radio-button-on" : "radio-button-off"} size={20} color={selected === c.code ? colors.brandPrimary : colors.muted} />
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.onSurface, fontSize: fontSize.base }}>{c.name}</Text>
            {c.eta ? <Text style={co.paySub}>Estimasi {c.eta}</Text> : null}
          </View>
          <Text style={{ color: colors.onSurface, fontWeight: "600" }}>{c.cost ? formatIDR(c.cost) : "Gratis"}</Text>
        </Pressable>
      ))}
    </>
  );
}
