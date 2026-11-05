import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // ONNX Runtime is a native module; load it from node_modules at runtime instead of bundling it.
  serverExternalPackages: ["onnxruntime-node"],
  // The ONNX models in models/ are read at runtime by src/lib/classifier.ts.
  outputFileTracingIncludes: { "/api/**/*": ["./models/**/*"] },
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
