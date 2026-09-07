import { defineConfig, loadEnv } from "vite";

const DEFAULT_API_BASE = "/api";
const DEFAULT_BRIDGE_TARGET = "http://127.0.0.1:8765";

function bridgeTarget(configuredValue: string | undefined): string {
  const configured = configuredValue?.trim() || DEFAULT_BRIDGE_TARGET;
  const url = new URL(configured);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("VITE_BRIDGE_TARGET deve usare http o https");
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error(
      "VITE_BRIDGE_TARGET non può contenere credenziali, query o fragment",
    );
  }
  return url.toString().replace(/\/$/, "");
}

function apiProxyPrefix(configuredValue: string | undefined): string | null {
  const configured = configuredValue?.trim() || DEFAULT_API_BASE;
  if (/^[a-zA-Z][a-zA-Z\d+.-]*:/.test(configured)) return null;

  const url = new URL(`/${configured.replace(/^\/+/, "")}`, "http://vite.local");
  if (url.search || url.hash) {
    throw new Error("VITE_API_BASE non può contenere query o fragment");
  }

  const prefix = url.pathname.replace(/\/+$/, "");
  if (!prefix) {
    throw new Error("VITE_API_BASE deve avere un prefisso non-root per il proxy Vite");
  }
  return prefix;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, import.meta.dirname, "VITE_");
  const target = bridgeTarget(env.VITE_BRIDGE_TARGET);
  const proxyPrefix = apiProxyPrefix(env.VITE_API_BASE);

  return {
    root: import.meta.dirname,
    server: {
      port: 5173,
      proxy: proxyPrefix
        ? {
            [proxyPrefix]: {
              target,
              changeOrigin: true,
              rewrite: (path) =>
                path.replace(
                  new RegExp(`^${escapeRegExp(proxyPrefix)}(?=/|$)`),
                  "",
                ),
            },
          }
        : undefined,
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(moduleId) {
            const id = moduleId.replaceAll("\\", "/");
            if (!id.includes("/node_modules/")) return undefined;
            if (id.includes("/node_modules/three/examples/")) {
              return "vendor-three-extras";
            }
            if (id.includes("/node_modules/three/build/three.core")) {
              return "vendor-three-core";
            }
            if (id.includes("/node_modules/three/")) {
              return "vendor-three-renderer";
            }
            if (
              id.includes("/node_modules/d3-") ||
              id.includes("/node_modules/ngraph.") ||
              id.includes("/node_modules/internmap/") ||
              id.includes("/node_modules/delaunator/") ||
              id.includes("/node_modules/robust-predicates/")
            ) {
              return "vendor-layout";
            }
            return "vendor-graph";
          },
        },
      },
    },
  };
});
