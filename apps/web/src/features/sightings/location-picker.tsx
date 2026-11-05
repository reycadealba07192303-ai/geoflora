"use client";
import { useEffect, useRef } from "react";
import type { Map as LeafletMap, Marker } from "leaflet";
import "leaflet/dist/leaflet.css";

const PHILIPPINES: [number, number] = [12.8797, 121.774];
const valid = (latitude: string, longitude: string) => {
  const lat = Number(latitude), lng = Number(longitude);
  return latitude !== "" && longitude !== "" && Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180 ? [lat, lng] as [number, number] : null;
};

// Click or drag the pin to set where the plant was found. Coordinates stay editable in the form fields.
export default function LocationPicker({ latitude, longitude, onPick }: { latitude: string; longitude: string; onPick: (latitude: number, longitude: number) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null), marker = useRef<Marker | null>(null);
  const pick = useRef(onPick);
  pick.current = onPick;
  const leaflet = useRef<typeof import("leaflet") | null>(null);

  useEffect(() => {
    let disposed = false;
    import("leaflet").then(L => {
      if (disposed || !container.current) return;
      leaflet.current = L;
      const start = valid(latitude, longitude);
      const instance = L.map(container.current).setView(start ?? PHILIPPINES, start ? 15 : 6);
      map.current = instance;
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19 }).addTo(instance);
      instance.on("click", event => pick.current(round(event.latlng.lat), round(event.latlng.lng)));
      if (start) place(start);
    });
    return () => { disposed = true; map.current?.remove(); map.current = null; marker.current = null; };
    // The map is created once; later coordinate changes move the pin below.
  }, []);

  function place(position: [number, number]) {
    const L = leaflet.current, instance = map.current;
    if (!L || !instance) return;
    if (!marker.current) {
      const icon = L.divIcon({ className: "location-pin", html: "<span></span>", iconSize: [26, 26], iconAnchor: [13, 26] });
      marker.current = L.marker(position, { draggable: true, icon, title: "Plant location", alt: "Selected plant location", keyboard: true }).addTo(instance);
      marker.current.on("dragend", () => { const point = marker.current!.getLatLng(); pick.current(round(point.lat), round(point.lng)); });
    } else marker.current.setLatLng(position);
  }

  useEffect(() => {
    const position = valid(latitude, longitude);
    if (!position || !map.current) return;
    place(position);
    if (!map.current.getBounds().contains(position)) map.current.setView(position, Math.max(map.current.getZoom(), 13));
  }, [latitude, longitude]);

  return <div ref={container} className="location-picker relative z-0 h-[clamp(240px,34svh,340px)] w-full overflow-hidden rounded-[20px]" role="application" aria-label="Map for choosing the plant location. Click to place the pin, or drag it." data-latitude={latitude} data-longitude={longitude} />;
}

const round = (value: number) => Math.round(value * 1e6) / 1e6;
