import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/App";

const host = document.getElementById("root");
if (!host) {
  throw new Error("overlay root element is missing from index.html");
}

createRoot(host).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
