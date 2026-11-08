import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Icon from "@react-native-vector-icons/ionicons";
import * as ImagePicker from "expo-image-picker";

import { colors, fontSize, spacing } from "@/src/theme";
import { api, imgUrl } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { ScreenHeader } from "@/src/components/screen-header";
import { adminStyles, Card, Chips, Field, PrimaryButton } from "@/src/components/admin-form";

function Badge({ ok }: { ok: boolean }) {
  return (
    <View style={[styles.badge, { backgroundColor: ok ? colors.success : colors.warning }]}>
      <Icon name={ok ? "checkmark-circle" : "alert-circle"} size={12} color={colors.onSuccess} />
      <Text style={styles.badgeText}>{ok ? "Terverifikasi" : "Belum verifikasi"}</Text>
    </View>
  );
}

export default function Profile() {
  const insets = useSafeAreaInsets();
  const { user, setUser } = useAuth();
  const [name, setName] = useState(user?.name ?? "");
  const [gender, setGender] = useState(user?.gender ?? "");
  const [birthdate, setBirthdate] = useState(user?.birthdate ?? "");
  const [emailStep, setEmailStep] = useState(false);
  const [emailCode, setEmailCode] = useState("");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [phoneStep, setPhoneStep] = useState(false);
  const [phoneCode, setPhoneCode] = useState("");
  const [devCode, setDevCode] = useState("");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState({ err: "", ok: "" });

  useEffect(() => {
    if (!user) return;
    setName(user.name ?? "");
    setGender(user.gender ?? "");
    setBirthdate(user.birthdate ?? "");
    setPhone(user.phone ?? "");
  }, [user?.user_id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!user) return null;

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setMsg({ err: "", ok: "" });
    try { await fn(); } catch (e: any) { setMsg({ err: e.message, ok: "" }); } finally { setBusy(""); }
  };

  const pickAvatar = async () => {
    const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], allowsEditing: true, aspect: [1, 1], quality: 0.7 });
    if (r.canceled || !r.assets?.[0]) return;
    const a = r.assets[0];
    await run("avatar", async () => {
      setUser(await api.uploadAvatar({ uri: a.uri, name: a.fileName ?? "avatar.jpg", mimeType: a.mimeType ?? "image/jpeg" }));
      setMsg({ err: "", ok: "Foto profil diperbarui" });
    });
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[adminStyles.root, { paddingTop: insets.top }]} testID="profile-screen">
      <ScreenHeader title="Edit Profil" />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }} keyboardShouldPersistTaps="handled">
        <Pressable testID="avatar-pick" style={styles.avatarWrap} onPress={pickAvatar} disabled={busy === "avatar"}>
          <View style={styles.avatar}>
            {user.picture ? <Image source={imgUrl(user.picture)} style={styles.avatarImg} contentFit="cover" /> : (
              <Text style={styles.avatarText}>{user.name?.[0]?.toUpperCase() ?? "U"}</Text>
            )}
            {busy === "avatar" ? <View style={styles.avatarBusy}><ActivityIndicator color={colors.onBrandPrimary} /></View> : null}
          </View>
          <Text style={styles.link}>Ganti foto profil</Text>
        </Pressable>

        {msg.err ? <Text style={adminStyles.err} testID="profile-error">{msg.err}</Text> : null}
        {msg.ok ? <Text style={adminStyles.ok} testID="profile-ok">{msg.ok}</Text> : null}

        <Card>
          <Field testID="profile-name" label="Nama lengkap" value={name} onChangeText={setName} />
          <Text style={adminStyles.section}>Jenis kelamin</Text>
          <Chips testID="profile-gender" value={gender} onChange={setGender}
            options={[{ id: "male", label: "Laki-laki" }, { id: "female", label: "Perempuan" }]} />
          <Field testID="profile-birthdate" label="Tanggal lahir (TTTT-BB-HH)" value={birthdate} onChangeText={setBirthdate} placeholder="1990-01-31" />
          <PrimaryButton testID="profile-save" label="Simpan Profil" loading={busy === "profile"} onPress={() => run("profile", async () => {
            if (birthdate && !/^\d{4}-\d{2}-\d{2}$/.test(birthdate)) throw new Error("Format tanggal lahir TTTT-BB-HH");
            setUser(await api.updateProfile({ name: name.trim(), gender, birthdate }));
            setMsg({ err: "", ok: "Profil disimpan" });
          })} />
        </Card>

        <Card>
          <View style={styles.between}>
            <View style={{ flex: 1 }}>
              <Text style={adminStyles.section}>Email</Text>
              <Text style={styles.value}>{user.email}</Text>
            </View>
            <Badge ok={user.email_verified} />
          </View>
          {!user.email_verified ? (emailStep ? (
            <>
              <Field testID="email-code" label="Kode dari email" value={emailCode} keyboardType="number-pad"
                onChangeText={(t) => setEmailCode(t.replace(/\D/g, "").slice(0, 6))} placeholder="123456" />
              <PrimaryButton testID="email-verify-confirm" label="Verifikasi Email" loading={busy === "ev2"} onPress={() => run("ev2", async () => {
                setUser(await api.verifyEmailConfirm(emailCode));
                setEmailStep(false);
                setMsg({ err: "", ok: "Email terverifikasi" });
              })} />
            </>
          ) : (
            <PrimaryButton testID="email-verify-send" label="Kirim Kode Verifikasi" variant="outline" loading={busy === "ev1"} onPress={() => run("ev1", async () => {
              const r = await api.verifyEmailRequest();
              setEmailStep(true);
              setMsg({ err: "", ok: r.message });
            })} />
          )) : null}
        </Card>

        <Card>
          <View style={styles.between}>
            <View style={{ flex: 1 }}>
              <Text style={adminStyles.section}>Nomor HP (WhatsApp)</Text>
              <Text style={styles.value}>{user.phone ? `+${user.phone}` : "Belum diisi"}</Text>
            </View>
            <Badge ok={user.phone_verified} />
          </View>
          <Field testID="phone-input" label={user.phone_verified ? "Ganti nomor HP" : "Nomor HP"} value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="0812xxxxxxx" />
          {phoneStep ? (
            <>
              {devCode ? <Text style={styles.dev} testID="phone-dev-code">Mode uji — kode OTP: {devCode}</Text> : null}
              <Field testID="phone-code" label="Kode OTP" value={phoneCode} keyboardType="number-pad"
                onChangeText={(t) => setPhoneCode(t.replace(/\D/g, "").slice(0, 6))} placeholder="123456" />
              <PrimaryButton testID="phone-verify-confirm" label="Verifikasi Nomor" loading={busy === "pv2"} onPress={() => run("pv2", async () => {
                setUser(await api.phoneConfirm(phoneCode));
                setPhoneStep(false);
                setDevCode("");
                setMsg({ err: "", ok: "Nomor HP terverifikasi" });
              })} />
            </>
          ) : null}
          <PrimaryButton testID="phone-verify-send" label={phoneStep ? "Kirim ulang OTP" : "Kirim OTP via WhatsApp"} variant="outline" loading={busy === "pv1"} onPress={() => run("pv1", async () => {
            const r = await api.phoneRequest(phone);
            setPhoneStep(true);
            setDevCode(r.dev_code ?? "");
            setMsg({ err: "", ok: r.message });
          })} />
        </Card>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  avatarWrap: { alignItems: "center", gap: spacing.sm },
  avatar: { width: 96, height: 96, borderRadius: 48, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  avatarImg: { width: 96, height: 96 },
  avatarText: { color: colors.onBrandPrimary, fontSize: 36, fontWeight: "600" },
  avatarBusy: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, backgroundColor: "rgba(0,0,0,0.4)", alignItems: "center", justifyContent: "center" },
  link: { color: colors.brandPrimary, fontSize: fontSize.sm, fontWeight: "500" },
  between: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  value: { fontSize: fontSize.base, color: colors.onSurface, marginTop: 2 },
  badge: { flexDirection: "row", alignItems: "center", gap: 4, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 },
  badgeText: { color: colors.onSuccess, fontSize: 11, fontWeight: "600" },
  dev: { backgroundColor: colors.brandTertiary, color: colors.brandPrimary, padding: spacing.sm, borderRadius: 8, fontWeight: "600" },
});
