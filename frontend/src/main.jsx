import * as Sentry from "@sentry/react";
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

Sentry.init({
  dsn: "https://8887b61f540d061f01e7ce1f965c5e18@o4511017293971456.ingest.de.sentry.io/4511053000409168",
  dsn: import.meta.env.VITE_SENTRY_DSN || "",
  sendDefaultPii: true,
});

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>
)