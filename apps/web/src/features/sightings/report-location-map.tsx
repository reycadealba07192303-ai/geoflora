"use client";
import { useEffect, useRef } from "react";
import "leaflet/dist/leaflet.css";

export default function ReportLocationMap({ id, latitude, longitude }: { id: string; latitude: number; longitude: number }) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false;
    let map: import("leaflet").Map | undefined;
    import("leaflet").then(L => {
      if (cancelled || !container.current) return;
      map = L.map(container.current).setView([latitude, longitude], 15);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19 }).addTo(map);
      const photo = document.createElement("img");
      photo.src = `/api/sightings/${id}/photo?thumbnail=1`; photo.alt = "Plant photographed at this location";
      photo.style.cssText = "width:56px;height:56px;object-fit:cover;border:3px solid white;border-radius:13px;box-shadow:0 3px 12px #0005";
      const icon = L.divIcon({ html: photo, className: "sighting-photo-marker", iconSize: [56, 56], iconAnchor: [28, 28] });
      L.marker([latitude, longitude], { icon, title: "Plant sighting location", alt: "Photo of the reported plant at its recorded location" }).addTo(map);
    });
    return () => { cancelled = true; map?.remove(); };
  }, [id, latitude, longitude]);
  return <div ref={container} className="report-location-map relative z-0 h-[clamp(260px,40svh,380px)] w-full" data-latitude={latitude} data-longitude={longitude} aria-label="Map showing the plant photo at its recorded location" />;
}
