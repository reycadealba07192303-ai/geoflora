// Phone photos are often 5–12 MB, above the 4.5 MB a hosted request may carry (Vercel). Large photos are redrawn as an
// upright JPEG of at most 2048 px on a side, still far more detail than identification or review needs. Small photos,
// and any the browser cannot decode, are sent as they are.
const KEEP_BELOW_BYTES = 3 * 1024 * 1024;
const MAX_SIDE = 2048;

export async function shrinkPhoto(file: File): Promise<File> {
  if (file.size <= KEEP_BELOW_BYTES || typeof createImageBitmap !== "function") return file;
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    for (const quality of [0.9, 0.8, 0.7]) {
      const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/jpeg", quality));
      if (blob && blob.size <= KEEP_BELOW_BYTES) return new File([blob], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg", lastModified: file.lastModified });
    }
  } catch { /* Fall back to the original photo. */ }
  return file;
}
