import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";
import runtimeErrorOverlay from "@replit/vite-plugin-runtime-error-modal";
import { mockupPreviewPlugin } from "./mockupPreviewPlugin";
import http from "http";

const rawPort = process.env.PORT;

if (!rawPort) {
  throw new Error(
    "PORT environment variable is required but was not provided.",
  );
}

const port = Number(rawPort);

if (Number.isNaN(port) || port <= 0) {
  throw new Error(`Invalid PORT value: "${rawPort}"`);
}

const basePath = process.env.BASE_PATH;

if (!basePath) {
  throw new Error(
    "BASE_PATH environment variable is required but was not provided.",
  );
}

// Proxy all non-mockup-sandbox requests to Flask (port 5000).
// This makes the Vite server transparently serve the Flask app at the root,
// while keeping /__mockup/preview/* and Vite internals handled by Vite.
function flaskProxyPlugin(): import("vite").Plugin {
  return {
    name: "flask-proxy",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? "/";

        // Always let Vite handle its own internal routes
        if (
          url.startsWith("/@") ||
          url.startsWith("/__vite") ||
          url.startsWith("/node_modules/")
        ) {
          next();
          return;
        }

        // Determine Flask path to forward to
        let flaskPath: string | null = null;

        if (url === basePath || url === basePath + "/") {
          // Mockup root → Flask root
          flaskPath = "/";
        } else if (!url.startsWith(basePath + "/")) {
          // Any path outside of the basePath subtree → proxy as-is to Flask
          flaskPath = url;
        }
        // Paths under /__mockup/* (assets, preview, src, etc.) → let Vite handle

        if (flaskPath !== null) {
          const proxyReq = http.request(
            {
              hostname: "localhost",
              port: 5000,
              path: flaskPath,
              method: req.method ?? "GET",
              headers: { ...req.headers, host: "localhost:5000" },
            },
            (proxyRes) => {
              const headers: Record<string, string | string[] | undefined> = {};
              for (const [k, v] of Object.entries(proxyRes.headers)) {
                if (v !== undefined) headers[k] = v;
              }
              res.writeHead(proxyRes.statusCode ?? 200, headers as never);
              proxyRes.pipe(res, { end: true });
            },
          );

          proxyReq.on("error", () => {
            res.writeHead(502);
            res.end("Flask unavailable — is the АС СКЛ workflow running?");
          });

          req.pipe(proxyReq, { end: true });
          return;
        }

        next();
      });
    },
  };
}

export default defineConfig({
  base: basePath,
  plugins: [
    flaskProxyPlugin(),
    mockupPreviewPlugin(),
    react(),
    tailwindcss(),
    runtimeErrorOverlay(),
    ...(process.env.NODE_ENV !== "production" &&
    process.env.REPL_ID !== undefined
      ? [
          await import("@replit/vite-plugin-cartographer").then((m) =>
            m.cartographer({
              root: path.resolve(import.meta.dirname, ".."),
            }),
          ),
        ]
      : []),
  ],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "src"),
    },
  },
  root: path.resolve(import.meta.dirname),
  build: {
    outDir: path.resolve(import.meta.dirname, "dist"),
    emptyOutDir: true,
  },
  server: {
    port,
    host: "0.0.0.0",
    allowedHosts: true,
    fs: {
      strict: true,
    },
  },
  preview: {
    port,
    host: "0.0.0.0",
    allowedHosts: true,
  },
});
