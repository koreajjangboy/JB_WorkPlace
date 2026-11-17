import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    // Windows에서 다른 프로그램(WorkPlace가 실행한 Claude 등)이 고친 파일을 놓치지 않도록 주기적으로 확인한다.
    watch: { usePolling: true, interval: 300 },
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
