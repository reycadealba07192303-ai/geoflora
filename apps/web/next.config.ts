import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // ONNX Runtime is a native module; load it from node_modules at runtime instead of bundling it.
  serverExternalPackages: ["onnxruntime-node"],
  // The ONNX models in models/ are read at runtime by src/lib/classifier.ts.
  // Only the routes that run the models carry them and ONNX Runtime's Linux library (libonnxruntime.so.1, which file
  // tracing misses); the others read just the small JSON files. Keeping the heavy files on few routes lets Vercel
  // bundle the API routes into few functions (Hobby plan: at most 12 per deployment).
  outputFileTracingIncludes: {
    "/api/**/*": ["./models/**/*.json"],
    "/api/identify": ["./models/**/*", "./node_modules/onnxruntime-node/bin/napi-v*/linux/x64/**"],
    "/api/admin/review": ["./models/**/*", "./node_modules/onnxruntime-node/bin/napi-v*/linux/x64/**"],
    "/api/admin/references/[reportId]": ["./models/**/*", "./node_modules/onnxruntime-node/bin/napi-v*/linux/x64/**"],
  },
  // Vercel runs Linux x64: leave out the Windows, macOS and Linux arm64 ONNX Runtime binaries (about 230 MB).
  outputFileTracingExcludes: { "/api/**/*": ["./node_modules/onnxruntime-node/bin/napi-v*/win32/**", "./node_modules/onnxruntime-node/bin/napi-v*/darwin/**", "./node_modules/onnxruntime-node/bin/napi-v*/linux/arm64/**"] },
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
