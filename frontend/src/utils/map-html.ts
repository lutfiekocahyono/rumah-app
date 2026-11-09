import type { CustomerLocation } from "@/src/api";

export type MapPoint = Pick<CustomerLocation, "lat" | "lng" | "name" | "email" | "phone" | "guest" | "orders" | "updated_at">;

/** Leaflet + OpenStreetMap page with one dot per customer (green = pernah belanja, orange = pelanggan, grey = tamu). */
export function mapHtml(points: MapPoint[], c: { buyer: string; customer: string; guest: string }): string {
  const data = JSON.stringify(points).replace(/</g, "\\u003c");
  return `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#m{margin:0;height:100%;font-family:sans-serif}.p b{display:block;margin-bottom:2px}</style></head>
<body><div id="m"></div><script>
var pts=${data};
var map=L.map('m',{zoomControl:true}).setView([-7.45,112.72],11);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(map);
function esc(s){return String(s||'').replace(/[&<>"]/g,function(x){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[x]})}
var b=[];
pts.forEach(function(p){
  var col=p.guest?'${c.guest}':(p.orders?'${c.buyer}':'${c.customer}');
  var m=L.circleMarker([p.lat,p.lng],{radius:7,color:'#fff',weight:2,fillColor:col,fillOpacity:0.9}).addTo(map);
  m.bindPopup('<div class="p"><b>'+esc(p.name)+'</b>'+(p.email?esc(p.email)+'<br>':'')+(p.phone?esc(p.phone)+'<br>':'')+
    (p.guest?'Tamu (belum masuk)':(p.orders+' pesanan'))+'<br>Terakhir: '+esc(new Date(p.updated_at+(String(p.updated_at).endsWith('Z')?'':'Z')).toLocaleString('id-ID'))+'</div>');
  b.push([p.lat,p.lng]);
});
if(b.length===1)map.setView(b[0],14);else if(b.length)map.fitBounds(b,{padding:[30,30],maxZoom:15});
</script></body></html>`;
}
