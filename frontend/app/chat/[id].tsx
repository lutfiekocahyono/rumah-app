import React, { useCallback, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, ActivityIndicator, TextInput, AppState, Image } from "react-native";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing, formatIDR } from "@/src/theme";
import { api, type ChatMessage, type ChatThread } from "@/src/api";
import { ScreenHeader } from "@/src/components/screen-header";
import { fmtDate } from "@/src/utils/date";

const POLL_MS = 4000;

export default function ChatThreadScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const [thread, setThread] = useState<Omit<ChatThread, "messages"> | null>(null);
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState("");
  const lastAt = useRef<string | undefined>(undefined);

  const merge = (incoming: ChatMessage[]) => {
    if (!incoming.length) return;
    setMsgs((m) => {
      const seen = new Set(m.map((x) => x.msg_id));
      return [...m, ...incoming.filter((x) => !seen.has(x.msg_id))];
    });
  };

  const poll = useCallback(async () => {
    if (!id) return;
    try {
      const t = await api.chatThread(id, lastAt.current);
      setThread({ conversation: t.conversation, me: t.me });
      if (t.messages.length) lastAt.current = t.messages[t.messages.length - 1].created_at;
      merge(t.messages);
      setErr("");
    } catch (e: any) { setErr(e.message); }
  }, [id]);

  useFocusEffect(useCallback(() => {
    void poll();
    let timer = setInterval(poll, POLL_MS);
    const sub = AppState.addEventListener("change", (s) => {
      clearInterval(timer);
      if (s === "active") { void poll(); timer = setInterval(poll, POLL_MS); }
    });
    return () => { clearInterval(timer); sub.remove(); };
  }, [poll]));

  const send = async () => {
    const t = text.trim();
    if (!t || !id) return;
    setSending(true);
    try { merge([await api.sendChat(id, t)]); setText(""); void poll(); } catch (e: any) { setErr(e.message); } finally { setSending(false); }
  };

  const title = thread ? (thread.me === "store" ? thread.conversation.user_name : thread.conversation.store_name) : "Chat";
  const reversed = [...msgs].reverse();

  return (
    <View style={[styles.root, { paddingTop: insets.top }]} testID="chat-thread-screen">
      <ScreenHeader title={title} />
      <KeyboardAvoidingView behavior="padding" style={{ flex: 1 }}>
        {!thread && !err ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} /> : (
          <FlatList
            data={reversed}
            inverted
            keyExtractor={(m) => m.msg_id}
            contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm }}
            keyboardShouldPersistTaps="handled"
            ListFooterComponent={
              <Text style={styles.info}>
                {thread?.me === "store" ? "Chat dengan pembeli. Balas dengan sopan & jelas." : "Chat langsung dengan toko yang menangani pesanan Anda."}
              </Text>
            }
            renderItem={({ item: m }) => {
              const mine = m.sender === thread?.me;
              return (
                <View style={[styles.bubble, mine ? styles.mine : styles.theirs]} testID={`chat-msg-${m.msg_id}`}>
                  {m.product ? (
                    <Pressable testID="chat-product-card" style={styles.card} onPress={() => router.push(`/product/${m.product!.product_id}` as any)}>
                      {m.product.image ? <Image source={{ uri: m.product.image }} style={styles.cardImg} /> : <View style={[styles.cardImg, { backgroundColor: colors.surfaceTertiary }]} />}
                      <View style={{ flex: 1, gap: 2 }}>
                        <Text style={styles.cardName} numberOfLines={3} testID="chat-product-name">{m.product.name}</Text>
                        <Text style={styles.cardPrice}>{formatIDR(m.product.price)}</Text>
                        {m.product.sku ? <Text style={styles.time}>SKU {m.product.sku}</Text> : null}
                      </View>
                    </Pressable>
                  ) : null}
                  <Text style={[styles.msg, mine && { color: colors.onBrandPrimary }]}>{m.text}</Text>
                  <Text style={[styles.time, mine && { color: colors.onBrandPrimary, opacity: 0.8 }]}>{fmtDate(m.created_at)}</Text>
                </View>
              );
            }}
          />
        )}
        {err ? <Text style={styles.err} testID="chat-error">{err}</Text> : null}
        <View style={[styles.inputBar, { paddingBottom: Math.max(spacing.sm, insets.bottom) }]}>
          <TextInput
            testID="chat-input"
            value={text}
            onChangeText={setText}
            placeholder="Tulis pesan…"
            placeholderTextColor={colors.muted}
            multiline
            maxLength={1000}
            style={styles.input}
          />
          <Pressable testID="chat-send" style={[styles.send, !text.trim() && { opacity: 0.5 }]} disabled={sending || !text.trim()} onPress={send}>
            {sending ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Icon name="send" size={18} color={colors.onBrandPrimary} />}
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceSecondary },
  info: { textAlign: "center", fontSize: 12, color: colors.muted, marginBottom: spacing.md },
  bubble: { maxWidth: "80%", borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, gap: 2 },
  mine: { alignSelf: "flex-end", backgroundColor: colors.brandPrimary, borderBottomRightRadius: 4 },
  theirs: { alignSelf: "flex-start", backgroundColor: colors.surface, borderBottomLeftRadius: 4, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  msg: { fontSize: fontSize.base, color: colors.onSurface },
  time: { fontSize: 10, color: colors.muted, alignSelf: "flex-end" },
  card: { flexDirection: "row", gap: spacing.sm, padding: spacing.sm, borderRadius: radius.sm, backgroundColor: colors.surface, marginBottom: 4, minWidth: 220 },
  cardImg: { width: 56, height: 56, borderRadius: radius.sm },
  cardName: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  cardPrice: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary },
  err: { color: colors.error, fontSize: fontSize.sm, paddingHorizontal: spacing.lg },
  inputBar: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm, paddingHorizontal: spacing.md, paddingTop: spacing.sm, backgroundColor: colors.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  input: { flex: 1, maxHeight: 120, minHeight: 44, backgroundColor: colors.surfaceTertiary, borderRadius: 22, paddingHorizontal: spacing.md, paddingTop: 12, paddingBottom: 12, fontSize: fontSize.base, color: colors.onSurface },
  send: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
});
