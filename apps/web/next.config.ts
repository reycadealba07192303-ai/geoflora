import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // ONNX Runtime is a native module; load it from node_modules at runtime instead of bundling it.
  serverExternalPackages: ["onnxruntime-node"],
  // The ONNX models in models/ are read at runtime by src/lib/classifier.ts.
  // Also include ONNX Runtime's Linux shared library (libonnxruntime.so.1): file tracing finds only the .node binding.
  outputFileTracingIncludes: { "/api/**/*": ["./models/**/*", "./node_modules/onnxruntime-node/bin/napi-v*/linux/x64/**"] },
  // Vercel runs Linux x64: leave out the Windows, macOS and Linux arm64 ONNX Runtime binaries (about 230 MB).
  outputFileTracingExcludes: { "/api/**/*": ["./node_modules/onnxruntime-node/bin/napi-v*/win32/**", "./node_modules/onnxruntime-node/bin/napi-v*/darwin/**", "./node_modules/onnxruntime-node/bin/napi-v*/linux/arm64/**"] },
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
