import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

// Apply saved theme before first render to avoid flash
const savedTheme = localStorage.getItem('edon_theme') ?? 'dark';
document.documentElement.classList.add(savedTheme);

createRoot(document.getElementById("root")!).render(<App />);
