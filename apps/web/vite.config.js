import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
export default defineConfig({
    plugins: [
        react(),
        VitePWA({
            registerType: "autoUpdate",
            includeAssets: ["retainai-mark.svg"],
            manifest: {
                name: "RetainAI",
                short_name: "RetainAI",
                description: "Operational retention intelligence for NGO teams",
                theme_color: "#102032",
                background_color: "#f5efe4",
                display: "standalone",
                start_url: "/",
                icons: [
                    {
                        src: "/retainai-mark.svg",
                        sizes: "any",
                        type: "image/svg+xml",
                        purpose: "any",
                    },
                ],
            },
            workbox: {
                globPatterns: ["**/*.{js,css,html,svg,png}"],
                runtimeCaching: [
                    {
                        urlPattern: /^https?:\/\/.*\/api\/v1\/.*/i,
                        handler: "NetworkFirst",
                        options: {
                            cacheName: "retainai-api-cache",
                            expiration: {
                                maxEntries: 30,
                                maxAgeSeconds: 60 * 60 * 6,
                            },
                        },
                    },
                ],
            },
        }),
    ],
    server: {
        host: "0.0.0.0",
        port: 5173,
    },
});
