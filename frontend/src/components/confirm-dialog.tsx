import React from "react";
import { Modal, View, Text, Pressable, StyleSheet, ActivityIndicator } from "react-native";

import { colors, fontSize, radius, spacing } from "@/src/theme";

/** Cross-platform confirmation popup (works on web, iOS, Android). */
export function ConfirmDialog({ visible, title, message, confirmLabel = "Ya, hapus", danger = true, loading, onConfirm, onCancel }: {
  visible: boolean; title: string; message?: string; confirmLabel?: string; danger?: boolean; loading?: boolean;
  onConfirm: () => void; onCancel: () => void;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <Pressable style={styles.backdrop} onPress={onCancel}>
        <Pressable style={styles.box} onPress={() => {}} testID="confirm-dialog">
          <Text style={styles.title}>{title}</Text>
          {message ? <Text style={styles.msg}>{message}</Text> : null}
          <View style={styles.row}>
            <Pressable testID="confirm-cancel" style={[styles.btn, styles.cancel]} onPress={onCancel}>
              <Text style={styles.cancelText}>Batal</Text>
            </Pressable>
            <Pressable testID="confirm-ok" style={[styles.btn, { backgroundColor: danger ? colors.error : colors.brandPrimary }]} onPress={onConfirm} disabled={loading}>
              {loading ? <ActivityIndicator color={colors.onError} /> : <Text style={styles.okText}>{confirmLabel}</Text>}
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", alignItems: "center", justifyContent: "center", padding: spacing.xl },
  box: { width: "100%", maxWidth: 360, backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  title: { fontSize: fontSize.lg, fontWeight: "600", color: colors.onSurface },
  msg: { fontSize: fontSize.sm, color: colors.onSurfaceSecondary },
  row: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  btn: { flex: 1, minHeight: 48, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  cancel: { borderWidth: 1, borderColor: colors.border },
  cancelText: { color: colors.onSurface, fontWeight: "500" },
  okText: { color: colors.onError, fontWeight: "600" },
});
