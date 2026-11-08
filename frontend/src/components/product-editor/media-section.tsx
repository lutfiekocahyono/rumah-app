import React, { useEffect, useRef, useState } from "react";
import { View, Text, Pressable, StyleSheet, Platform, Linking } from "react-native";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import Icon from "@react-native-vector-icons/ionicons";

import { colors, fontSize, radius, spacing } from "@/src/theme";
import { imgUrl } from "@/src/api";
import { uploadWithProgress } from "@/src/utils/upload-progress";
import { FieldError, Section, ui } from "./ui";

const IMG = ["image/jpeg", "image/png", "image/webp"];
const VID = ["video/mp4", "video/quicktime"];
const EXT: Record<string, string> = { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp", mp4: "video/mp4", mov: "video/quicktime" };
type Picked = { uri: string; name: string; mimeType: string; size?: number };
type Job = { id: string; name: string; progress: number; error?: string };

const typeOf = (name: string, mime?: string | null) => (mime && mime !== "application/octet-stream" ? mime : EXT[name.split(".").pop()?.toLowerCase() ?? ""] ?? "");
const fromAsset = (a: ImagePicker.ImagePickerAsset, fallback: string): Picked => {
  const name = a.fileName ?? a.uri.split("/").pop() ?? fallback;
  return { uri: a.uri, name, mimeType: typeOf(name, a.mimeType), size: a.fileSize };
};

export function MediaSection({ images, video, onImages, onVideo, error, maxImages, imageMb, videoMb }: {
  images: string[]; video: string; onImages: (f: (prev: string[]) => string[]) => void; onVideo: (u: string) => void;
  error?: string; maxImages: number; imageMb: number; videoMb: number;
}) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [msg, setMsg] = useState("");
  const [drag, setDrag] = useState(false);
  const dropRef = useRef<any>(null); // on web this is the DOM node of the drop zone
  const left = maxImages - images.length;

  const check = (f: Picked, kind: "image" | "video") => {
    const ok = kind === "image" ? IMG : VID;
    if (!ok.includes(f.mimeType)) return kind === "image" ? `${f.name}: format harus JPG, PNG, atau WEBP` : `${f.name}: format video harus MP4 atau MOV`;
    const mb = kind === "image" ? imageMb : videoMb;
    if (f.size && f.size > mb * 1024 * 1024) return `${f.name}: ukuran maksimal ${mb} MB (${(f.size / 1048576).toFixed(1)} MB)`;
    return "";
  };

  const run = async (f: Picked, done: (url: string) => void) => {
    const id = `${Date.now()}-${Math.random()}`;
    setJobs((j) => [...j, { id, name: f.name, progress: 0 }]);
    try {
      const r = await uploadWithProgress("/product-editor/upload", f, (p) => setJobs((j) => j.map((x) => (x.id === id ? { ...x, progress: p } : x))));
      done(r.url);
      setJobs((j) => j.filter((x) => x.id !== id));
    } catch (e: any) {
      setJobs((j) => j.map((x) => (x.id === id ? { ...x, error: e.message } : x)));
    }
  };

  const addFiles = async (files: Picked[]) => {
    setMsg("");
    const errs: string[] = [];
    const ok = files.filter((f) => { const e = check(f, "image"); if (e) errs.push(e); return !e; });
    if (ok.length > left) errs.push(`Maksimal ${maxImages} foto, ${ok.length - left} foto tidak ditambahkan`);
    setMsg(errs.join("\n"));
    for (const f of ok.slice(0, Math.max(0, left))) await run(f, (url) => onImages((p) => (p.length < maxImages ? [...p, url] : p)));
  };

  const pickImages = async () => {
    const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], allowsMultipleSelection: true, selectionLimit: Math.max(1, left), quality: 0.85 });
    if (!r.canceled) await addFiles(r.assets.map((a, i) => fromAsset(a, `foto-${i}.jpg`)));
  };

  const replace = async (idx: number) => {
    const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.85 });
    if (r.canceled || !r.assets[0]) return;
    const f = fromAsset(r.assets[0], "foto.jpg");
    const e = check(f, "image");
    if (e) return setMsg(e);
    await run(f, (url) => onImages((p) => p.map((x, i) => (i === idx ? url : x))));
  };

  const pickVideo = async () => {
    const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["videos"] });
    if (r.canceled || !r.assets[0]) return;
    const f = fromAsset(r.assets[0], "video.mp4");
    const e = check(f, "video");
    if (e) return setMsg(e);
    setMsg("");
    await run(f, onVideo);
  };

  const move = (i: number, to: number) => onImages((p) => {
    if (to < 0 || to >= p.length) return p;
    const n = [...p];
    const [x] = n.splice(i, 1);
    n.splice(to, 0, x);
    return n;
  });

  // Web: drag & drop photos from the computer onto the drop zone
  useEffect(() => {
    if (Platform.OS !== "web") return;
    const el = dropRef.current as unknown as HTMLElement | null;
    if (!el?.addEventListener) return;
    const over = (e: DragEvent) => { e.preventDefault(); setDrag(true); };
    const leave = () => setDrag(false);
    const drop = (e: DragEvent) => {
      e.preventDefault();
      setDrag(false);
      const files = Array.from(e.dataTransfer?.files ?? []);
      void addFiles(files.map((f) => ({ uri: URL.createObjectURL(f), name: f.name, mimeType: typeOf(f.name, f.type), size: f.size })));
    };
    el.addEventListener("dragover", over);
    el.addEventListener("dragleave", leave);
    el.addEventListener("drop", drop);
    return () => { el.removeEventListener("dragover", over); el.removeEventListener("dragleave", leave); el.removeEventListener("drop", drop); };
  });

  return (
    <Section title="Foto & Video" icon="images-outline" testID="pe-media"
      subtitle={`Maks. ${maxImages} foto (JPG/PNG/WEBP, ≤${imageMb} MB) dan 1 video (MP4/MOV, ≤${videoMb} MB). Foto pertama jadi foto utama.`}>
      <View style={styles.grid}>
        {images.map((u, i) => (
          <View key={u + i} style={styles.tile} testID={`pe-photo-${i}`}>
            <Image source={imgUrl(u)} style={styles.img} contentFit="cover" />
            {i === 0 ? <View style={styles.mainBadge}><Text style={styles.mainText}>Utama</Text></View> : null}
            <View style={styles.tools}>
              {i > 0 ? <Tool icon="star-outline" id={`pe-photo-main-${i}`} onPress={() => move(i, 0)} /> : null}
              <Tool icon="chevron-back" id={`pe-photo-left-${i}`} onPress={() => move(i, i - 1)} disabled={i === 0} />
              <Tool icon="chevron-forward" id={`pe-photo-right-${i}`} onPress={() => move(i, i + 1)} disabled={i === images.length - 1} />
              <Tool icon="swap-horizontal" id={`pe-photo-replace-${i}`} onPress={() => replace(i)} />
              <Tool icon="trash-outline" id={`pe-photo-remove-${i}`} onPress={() => onImages((p) => p.filter((_, j) => j !== i))} danger />
            </View>
          </View>
        ))}
        {left > 0 ? (
          <Pressable ref={dropRef} testID="pe-photo-add" onPress={pickImages} style={[styles.tile, styles.drop, drag && styles.dropOn, !!error && { borderColor: colors.error }]}>
            <Icon name="cloud-upload-outline" size={28} color={colors.brandPrimary} />
            <Text style={styles.dropText}>{Platform.OS === "web" ? "Klik atau tarik foto ke sini" : "Tambah foto"}</Text>
            <Text style={ui.hint}>{images.length}/{maxImages}</Text>
          </Pressable>
        ) : null}
      </View>
      <FieldError msg={error} testID="pe-images-error" />
      {jobs.map((j) => (
        <View key={j.id} style={{ gap: 4 }} testID="pe-upload-job">
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Text style={[ui.hint, { flex: 1 }]} numberOfLines={1}>{j.error ? `Gagal: ${j.name}` : `Mengunggah ${j.name}`}</Text>
            {j.error ? <Pressable onPress={() => setJobs((x) => x.filter((y) => y.id !== j.id))}><Text style={styles.link}>Tutup</Text></Pressable> : <Text style={ui.hint}>{Math.round(j.progress * 100)}%</Text>}
          </View>
          {j.error ? <FieldError msg={j.error} /> : <View style={styles.bar}><View style={[styles.barFill, { width: `${Math.max(4, j.progress * 100)}%` }]} /></View>}
        </View>
      ))}
      {msg ? <FieldError msg={msg} testID="pe-media-msg" /> : null}

      <View style={styles.videoRow} testID="pe-video">
        <Icon name="videocam-outline" size={22} color={colors.brandPrimary} />
        <View style={{ flex: 1 }}>
          <Text style={ui.label}>Video produk (opsional)</Text>
          <Text style={ui.hint} numberOfLines={1}>{video ? "Video terunggah" : `MP4/MOV, maks. ${videoMb} MB`}</Text>
        </View>
        {video ? (
          <>
            <Pressable testID="pe-video-open" onPress={() => Linking.openURL(imgUrl(video))}><Text style={styles.link}>Putar</Text></Pressable>
            <Pressable testID="pe-video-replace" onPress={pickVideo}><Text style={styles.link}>Ganti</Text></Pressable>
            <Pressable testID="pe-video-remove" onPress={() => onVideo("")}><Text style={[styles.link, { color: colors.error }]}>Hapus</Text></Pressable>
          </>
        ) : (
          <Pressable testID="pe-video-add" onPress={pickVideo} style={styles.vidBtn}><Text style={styles.link}>Unggah video</Text></Pressable>
        )}
      </View>
    </Section>
  );
}

function Tool({ icon, id, onPress, disabled, danger }: { icon: string; id: string; onPress: () => void; disabled?: boolean; danger?: boolean }) {
  return (
    <Pressable testID={id} onPress={onPress} disabled={disabled} hitSlop={4} style={[styles.tool, disabled && { opacity: 0.35 }]}>
      <Icon name={icon as any} size={15} color={danger ? colors.error : colors.onSurface} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  tile: { width: 132, height: 160, borderRadius: radius.sm, overflow: "hidden", backgroundColor: colors.surfaceTertiary },
  img: { width: 132, height: 124 },
  mainBadge: { position: "absolute", top: 6, left: 6, backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 2 },
  mainText: { color: colors.onBrandPrimary, fontSize: 11, fontWeight: "700" },
  tools: { flexDirection: "row", justifyContent: "space-around", alignItems: "center", height: 36, backgroundColor: colors.surface },
  tool: { width: 24, height: 32, alignItems: "center", justifyContent: "center" },
  drop: { alignItems: "center", justifyContent: "center", gap: 4, borderWidth: 1.5, borderStyle: "dashed", borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary, padding: spacing.sm },
  dropOn: { borderStyle: "solid", opacity: 0.8 },
  dropText: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600", textAlign: "center" },
  bar: { height: 6, borderRadius: 3, backgroundColor: colors.surfaceTertiary, overflow: "hidden" },
  barFill: { height: 6, backgroundColor: colors.brandPrimary },
  videoRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary, flexWrap: "wrap" },
  vidBtn: { minHeight: 40, justifyContent: "center" },
  link: { color: colors.brandPrimary, fontWeight: "600", fontSize: fontSize.sm, paddingHorizontal: 4, paddingVertical: 8 },
});
