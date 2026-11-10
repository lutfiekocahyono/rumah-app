import React, { useEffect, useRef } from "react";
import { StyleProp, ViewStyle } from "react-native";
import { WebView } from "react-native-webview";

export type MapCmd = { type: "set"; lat: number; lng: number; seq: number } | { type: "clear"; seq: number } | null;
type Props = { html: string; cmd: MapCmd; onMessage: (data: string) => void; style?: StyleProp<ViewStyle>; testID?: string };

/** Native: Leaflet map page in a WebView. */
export function MapFrame({ html, cmd, onMessage, style, testID }: Props) {
  const ref = useRef<WebView>(null);
  useEffect(() => {
    if (cmd) ref.current?.injectJavaScript(`window.__cmd && window.__cmd(${JSON.stringify(cmd)}); true;`);
  }, [cmd]);
  return (
    <WebView ref={ref} testID={testID} style={style} originWhitelist={["*"]} javaScriptEnabled nestedScrollEnabled
      source={{ html, baseUrl: process.env.EXPO_PUBLIC_BACKEND_URL ?? "https://localhost" }}
      onMessage={(e) => onMessage(e.nativeEvent.data)} />
  );
}
