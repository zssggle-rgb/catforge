import React from "react";
import ReactDOM from "react-dom/client";
import { productTitle } from "./gtm/brand";
import hunterIcon from "./gtm/assets/rival-hunter-icon.svg";
const pathname = window.location.pathname;
const isGtm = ["/", "/gtm", "/gtm/"].includes(pathname);
if (isGtm) {
  document.title = productTitle;
  const icon = document.createElement("link");
  icon.rel = "icon";
  icon.type = "image/svg+xml";
  icon.href = hunterIcon;
  document.head.append(icon);
}
const App = isGtm ? React.lazy(() => import("./gtm/GtmApp")) : React.lazy(() => import("./FactoryRoot"));

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <React.Suspense fallback={<p role="status">正在打开工作台…</p>}>
      <App />
    </React.Suspense>
  </React.StrictMode>
);

