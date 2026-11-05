import { createHash } from "node:crypto";
import sharp from "sharp";
import mongoose from "mongoose";
import { connectDatabase } from "./sightings";

const schema = new mongoose.Schema({ ownerId: { type: String, required: true }, photoHash: { type: String, required: true }, sourceHash: { type: String, required: true }, result: { type: mongoose.Schema.Types.Mixed, required: true }, expiresAt: { type: Date, expires: 0, required: true } });
export const photoHash = (value: Buffer) => createHash("sha256").update(value).digest("hex");
export async function normalizePhoto(input: Buffer) {
  const metadata = await sharp(input, { limitInputPixels: 40_000_000 }).metadata();
  if (!["jpeg", "png", "webp"].includes(metadata.format ?? "") || !metadata.width || !metadata.height || Math.min(metadata.width, metadata.height) < 64) throw Error("Invalid plant photo");
  return sharp(input, { limitInputPixels: 40_000_000 }).rotate().resize({ width: 1600, height: 1600, fit: "inside", withoutEnlargement: true }).jpeg({ quality: 85 }).toBuffer();
}
export async function identifications() {
  await connectDatabase();
  type Identification = mongoose.InferSchemaType<typeof schema>;
  return (mongoose.models.Identification as mongoose.Model<Identification> | undefined) ?? mongoose.model<Identification>("Identification", schema);
}
export async function rememberIdentification(ownerId: string, input: Buffer, result: object) {
  const model = await identifications();
  const saved = await model.create({ ownerId, sourceHash: photoHash(input), photoHash: photoHash(await normalizePhoto(input)), result, expiresAt: new Date(Date.now() + 24 * 60 * 60_000) });
  return { ...result, identification_id: String(saved._id) };
}
