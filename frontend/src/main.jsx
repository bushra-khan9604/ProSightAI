import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import AuthApp from "./AuthApp";
import "./styles.css";
import "./upload.css";
import "./theme-refresh.css";
import "./auth.css";
import "./public-site/public-site.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode><BrowserRouter><AuthApp /></BrowserRouter></React.StrictMode>
);
