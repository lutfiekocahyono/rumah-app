import { Platform } from "react-native";
import * as Linking from "expo-linking";
import * as WebBrowser from "expo-web-browser";

WebBrowser.maybeCompleteAuthSession();

const AUTH_URL = "https://auth.emergentagent.com/?redirect=";

export function extractSessionId(url?: string | null): string | null {
  if (!url) return null;
  const m = url.match(/[?#&]session_id=([^&#]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

// Captured at module load so router redirects can't drop the hash first (web).
export const initialWebSessionId: string | null =
  Platform.OS === "web" && typeof window !== "undefined" ? extractSessionId(window.location.href) : null;

export function cleanWebUrl() {
  if (Platform.OS !== "web" || typeof window === "undefined") return;
  const url = new URL(window.location.href);
  url.searchParams.delete("session_id");
  const hash = url.hash.replace(/^#/, "").split("&").filter((p) => !p.startsWith("session_id=")).join("&");
  url.hash = hash ? `#${hash}` : "";
  window.history.replaceState(window.history.state, "", url.toString());
}

/** Opens Google sign-in. On web the page navigates away; on native resolves to a session_id (or null). */
export async function startGoogleLogin(): Promise<string | null> {
  if (Platform.OS === "web") {
    const redirect = window.location.origin + "/";
    window.location.href = AUTH_URL + encodeURIComponent(redirect);
    return null;
  }
  const redirect = Linking.createURL("");
  let captured: string | null = null;
  const sub = Linking.addEventListener("url", ({ url }) => {
    captured = extractSessionId(url) ?? captured;
  });
  try {
    const result = await WebBrowser.openAuthSessionAsync(AUTH_URL + encodeURIComponent(redirect), redirect);
    const fromResult = result.type === "success" ? extractSessionId(result.url) : null;
    return fromResult ?? captured ?? extractSessionId(await Linking.getInitialURL());
  } finally {
    sub.remove();
  }
}
