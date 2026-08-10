import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import ReviewerApp from "./ReviewerApp.jsx";
import "./index.css";

function Root() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";

  if (path === "/reviewer") {
    return <ReviewerApp />;
  }

  return <App />;
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
