import React, { useCallback } from "react";
import { useLocalSearchParams } from "expo-router";

import { api } from "@/src/api";
import { CourierEditor } from "@/src/components/courier-editor";

export default function AdminStoreCouriers() {
  const { id, name } = useLocalSearchParams<{ id: string; name?: string }>();
  const load = useCallback(() => api.adminCouriers(id!), [id]);
  const save = useCallback((c: Parameters<typeof api.adminSaveCouriers>[1]) => api.adminSaveCouriers(id!, c), [id]);
  return <CourierEditor title={`Tarif Kurir ${name ?? ""}`.trim()} load={load} save={save} />;
}
