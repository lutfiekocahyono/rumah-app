import React, { useEffect, useRef } from "react";
import { StyleProp, View, ViewStyle } from "react-native";

export type MapCmd = { type: "set"; lat: number; lng: number; seq: number } | { type: "clear"; seq: number } | null;
type Props = { html: string; cmd: MapCmd; onMessage: (data: string) => void; style?: StyleProp<ViewStyle>; testID?: string };

/** Web: Leaflet map page in an iframe. */
export function MapFrame({ html, cmd, onMessage, style, testID }: Props) {
  const ref = useRef<HTMLIFrameElement | null>(null);
  const cb = useRef(onMessage);
  cb.current = onMessage;
  useEffect(() => {
    const on = (e: MessageEvent) => {
      if (e.source === ref.current?.contentWindow && e.data && typeof e.data.__pgsmap === "string") cb.current(e.data.__pgsmap);
    };
    window.addEventListener("message", on);
    return () => window.removeEventListener("message", on);
  }, []);
  useEffect(() => { if (cmd) ref.current?.contentWindow?.postMessage(cmd, "*"); }, [cmd]);
  return (
    <View style={style} testID={testID}>
      {React.createElement("iframe", { ref, srcDoc: html, title: "Peta", style: { border: 0, width: "100%", height: "100%" } })}
    </View>
  );
}
