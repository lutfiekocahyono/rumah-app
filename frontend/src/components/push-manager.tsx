import React, { useEffect, useState } from "react";
import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import * as Device from "expo-device";
import * as Linking from "expo-linking";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useRouter } from "expo-router";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { ConfirmDialog } from "@/src/components/confirm-dialog";

const WEEK = 7 * 24 * 60 * 60 * 1000;

function openTarget(router: ReturnType<typeof useRouter>, data: Record<string, any> | undefined) {
  const url = data?.deeplink || data?.action_url;
  if (!url || typeof url !== "string") return;
  if (url.startsWith("http")) Linking.openURL(url); else router.push(url as any);
}

/** Push HP: buka layar saat notifikasi diketuk, daftarkan perangkat (hanya bila push diaktifkan admin), ajak buka Pengaturan bila izin ditolak. */
export function PushManager() {
  const router = useRouter();
  const { user } = useAuth();
  const [nudge, setNudge] = useState(false);

  useEffect(() => {
    if (Platform.OS === "web") return;
    const tapSub = Notifications.addNotificationResponseReceivedListener((r) => openTarget(router, r.notification.request.content.data));
    Notifications.getLastNotificationResponseAsync().then((r) => { if (r) openTarget(router, r.notification.request.content.data); }).catch(() => {});
    return () => tapSub.remove();
  }, [router]);

  useEffect(() => {
    if (Platform.OS === "web" || !user || !Device.isDevice) return;
    let cancelled = false;
    (async () => {
      try {
        if (!(await api.pushConfig()).enabled) return;  // push off (default): never prompt
        let perm = await Notifications.getPermissionsAsync();
        if (perm.status !== "granted" && perm.canAskAgain) perm = await Notifications.requestPermissionsAsync();
        if (perm.status !== "granted") {
          if (!perm.canAskAgain) {
            const last = await AsyncStorage.getItem("pushNudgeAt");
            if (!cancelled && (!last || Date.now() - Number(last) > WEEK)) setNudge(true);
          }
          return;
        }
        const token = await Notifications.getDevicePushTokenAsync();
        await api.registerPush(user.user_id, Platform.OS, String(token.data));
      } catch { /* push is optional; never block the app */ }
    })();
    return () => { cancelled = true; };
  }, [user]);

  const close = async (openSettings: boolean) => {
    setNudge(false);
    await AsyncStorage.setItem("pushNudgeAt", String(Date.now())).catch(() => {});
    if (openSettings) Linking.openSettings();
  };

  return (
    <ConfirmDialog visible={nudge} title="Aktifkan notifikasi?" danger={false} confirmLabel="Buka Pengaturan"
      message="Nyalakan izin notifikasi untuk menerima info produk baru, harga & stok dari Pusat Grosir Sidoarjo."
      onConfirm={() => close(true)} onCancel={() => close(false)} />
  );
}
