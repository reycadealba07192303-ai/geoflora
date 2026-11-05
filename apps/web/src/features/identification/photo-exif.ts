// Reads the camera's date/time and GPS position from a JPEG's EXIF block, in the browser, before the photo is shrunk
// (shrinking redraws the image and drops EXIF). Returns nothing for other formats or when the camera did not record it.
// Some phone browsers remove GPS from uploaded photos for privacy; the report then falls back to the device location.

export interface PhotoExif {
  takenAt?: string; // local date-time "YYYY-MM-DDTHH:MM:SS" as recorded by the camera (EXIF has no time zone)
  latitude?: number;
  longitude?: number;
}

const MAX_SCAN_BYTES = 256 * 1024; // EXIF lives in the first APP1 segment, near the start of the file

export async function readPhotoExif(file: File): Promise<PhotoExif> {
  if (file.type !== "image/jpeg") return {};
  try {
    const view = new DataView(await file.slice(0, MAX_SCAN_BYTES).arrayBuffer());
    if (view.getUint16(0) !== 0xffd8) return {};
    let offset = 2;
    while (offset + 4 <= view.byteLength) {
      const marker = view.getUint16(offset);
      const length = view.getUint16(offset + 2);
      if (marker === 0xffe1 && view.getUint32(offset + 4) === 0x45786966) return parseTiff(view, offset + 10);
      if ((marker & 0xff00) !== 0xff00 || marker === 0xffda) return {};
      offset += 2 + length;
    }
  } catch { /* Unreadable EXIF is treated as absent. */ }
  return {};
}

function parseTiff(view: DataView, start: number): PhotoExif {
  const little = view.getUint16(start) === 0x4949;
  const u16 = (at: number) => view.getUint16(start + at, little);
  const u32 = (at: number) => view.getUint32(start + at, little);
  const entries = (ifd: number) => {
    const out = new Map<number, { type: number; count: number; valueAt: number }>();
    const n = u16(ifd);
    for (let i = 0; i < n; i++) {
      const at = ifd + 2 + i * 12;
      const type = u16(at + 2), count = u32(at + 4);
      const size = ({ 1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8 } as Record<number, number>)[type] ?? 1;
      out.set(u16(at), { type, count, valueAt: size * count > 4 ? u32(at + 8) : at + 8 });
    }
    return out;
  };
  const ascii = (e?: { count: number; valueAt: number }) => e ? Array.from({ length: e.count }, (_, i) => String.fromCharCode(view.getUint8(start + e.valueAt + i))).join("").replace(/\0+$/, "") : "";
  const rationals = (e?: { count: number; valueAt: number }) => e ? Array.from({ length: e.count }, (_, i) => { const d = u32(e.valueAt + i * 8 + 4); return d ? u32(e.valueAt + i * 8) / d : NaN; }) : [];

  const result: PhotoExif = {};
  const ifd0 = entries(u32(4));
  const exifPointer = ifd0.get(0x8769), gpsPointer = ifd0.get(0x8825);
  const exif = exifPointer ? entries(u32(exifPointer.valueAt)) : new Map();
  const stamp = ascii(exif.get(0x9003)) || ascii(ifd0.get(0x0132));
  const match = /^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})/.exec(stamp);
  if (match && match[1] !== "0000") result.takenAt = `${match[1]}-${match[2]}-${match[3]}T${match[4]}:${match[5]}:${match[6]}`;
  if (gpsPointer) {
    const gps = entries(u32(gpsPointer.valueAt));
    const toDegrees = (parts: number[]) => parts.length === 3 && parts.every(Number.isFinite) ? parts[0] + parts[1] / 60 + parts[2] / 3600 : NaN;
    const lat = toDegrees(rationals(gps.get(2))) * (ascii(gps.get(1)) === "S" ? -1 : 1);
    const lon = toDegrees(rationals(gps.get(4))) * (ascii(gps.get(3)) === "W" ? -1 : 1);
    if (Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180 && !(lat === 0 && lon === 0)) {
      result.latitude = Math.round(lat * 1e6) / 1e6;
      result.longitude = Math.round(lon * 1e6) / 1e6;
    }
  }
  return result;
}
