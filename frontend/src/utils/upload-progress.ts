// Upload with progress. Web: XMLHttpRequest reports real byte progress. Native: expo/fetch has no
// progress events, so progress jumps 0 -> 1 when the request finishes.
import { Platform } from "react-native";
import { getToken } from "@/src/api";
import { fileNameFor, toFormDataPart, uploadForm, type LocalFile } from "@/src/utils/upload";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

export async function uploadWithProgress(path: string, file: LocalFile, onProgress: (p: number) => void): Promise<{ url: string }> {
  const token = await getToken();
  const url = `${BASE}/api${path}`;
  const fail = (status: number, body: string) => {
    let msg = `Upload gagal (HTTP ${status})`;
    try { msg = JSON.parse(body).detail || msg; } catch {}
    return new Error(status === 413 ? "File terlalu besar untuk diunggah" : msg);
  };
  if (Platform.OS === "web") {
    const form = new FormData();
    form.append("file", await toFormDataPart(file), fileNameFor(file));
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", url);
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
      xhr.onload = () => (xhr.status < 300 ? resolve(JSON.parse(xhr.responseText)) : reject(fail(xhr.status, xhr.responseText)));
      xhr.onerror = () => reject(new Error("Koneksi terputus saat upload"));
      xhr.send(form);
    });
  }
  const res = await uploadForm(url, { headers: token ? { Authorization: `Bearer ${token}` } : {}, files: { file } });
  const body = await res.text();
  if (!res.ok) throw fail(res.status, body);
  onProgress(1);
  return JSON.parse(body);
}
