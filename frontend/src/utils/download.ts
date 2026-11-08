import { Platform } from "react-native";
import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";

import { getToken } from "@/src/api";

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

/** Download an authenticated file: browser download on web, share sheet (save to Files / send) on phones. */
export async function downloadAuthed(url: string, fileName: string): Promise<void> {
  const token = await getToken();
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  if (Platform.OS === "web") {
    const res = await fetch(url, { headers });
    if (!res.ok) throw new Error(`Gagal mengunduh (HTTP ${res.status})`);
    const href = URL.createObjectURL(await res.blob());
    const a = (globalThis as any).document.createElement("a");
    a.href = href;
    a.download = fileName;
    a.click();
    setTimeout(() => URL.revokeObjectURL(href), 2000);
    return;
  }
  const file = await File.downloadFileAsync(url, new File(Paths.cache, fileName), { headers, idempotent: true });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(file.uri, { mimeType: XLSX, UTI: "org.openxmlformats.spreadsheetml.sheet", dialogTitle: fileName });
  }
}
