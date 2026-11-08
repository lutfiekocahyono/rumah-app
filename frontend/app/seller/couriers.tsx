import React from "react";

import { api } from "@/src/api";
import { CourierEditor } from "@/src/components/courier-editor";

export default function SellerCouriers() {
  return <CourierEditor title="Tarif Kurir Toko" load={api.sellerCouriers} save={api.sellerSaveCouriers} />;
}
