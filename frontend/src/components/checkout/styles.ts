import { StyleSheet } from "react-native";
import { colors, fontSize, radius, spacing } from "@/src/theme";

// Shared styles for the checkout screen and its sections
export const co = StyleSheet.create({
  section: { fontSize: fontSize.sm, color: colors.muted, marginBottom: spacing.sm },
  sectionGap: { marginTop: spacing.xl },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },

  label: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary, marginBottom: 4 },
  input: { backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.onSurface, fontSize: fontSize.base },

  payRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm },
  payLabel: { color: colors.onSurface, fontSize: fontSize.sm, fontWeight: "500" },
  paySub: { color: colors.muted, fontSize: 11, marginTop: 2 },
  payBtnText: { color: colors.onBrandPrimary, fontWeight: "500" },

  err: { color: colors.error, fontSize: fontSize.sm, marginTop: spacing.md },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  vChip: { flexDirection: "row", alignItems: "center", gap: 4, borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.md, minHeight: 34, backgroundColor: colors.brandTertiary },
  vChipText: { color: colors.brandPrimary, fontSize: 12, fontWeight: "600" },
});
