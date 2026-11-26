import React from "react";
import ReactDOM from "react-dom/client";
const pathname = window.location.pathname;
const isGtm = ["/", "/gtm", "/gtm/"].includes(pathname);
const App = isGtm ? React.lazy(() => import("./gtm/GtmApp")) : React.lazy(() => import("./FactoryRoot"));

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <React.Suspense fallback={<p role="status">正在打开工作台…</p>}>
      <App />
    </React.Suspense>
  </React.StrictMode>
);

