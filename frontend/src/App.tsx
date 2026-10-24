import React, { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { Navbar } from "./components/Navbar";
import { ToastProvider } from "./components/Toast";
import { Login } from "./pages/Login";
import { Generate } from "./pages/Generate";
import { PaperReview } from "./pages/PaperReview";
import { PaperPreview } from "./pages/PaperPreview";
import { PaperHistory } from "./pages/PaperHistory";
import { QuestionBank } from "./pages/QuestionBank";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      retry: 1,
    },
  },
});

const getInitialTheme = (): "dark" | "light" => {
  const saved = localStorage.getItem("edkonic_theme");
  if (saved === "light" || saved === "dark") {
    return saved;
  }
  if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: light)").matches) {
    return "light";
  }
  return "dark";
};

export default function App() {
  const [theme, setTheme] = useState<"dark" | "light">(getInitialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.classList.remove("dark", "light");
    document.documentElement.classList.add(theme);
    localStorage.setItem("edkonic_theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          <div className="bg-glow min-h-screen flex flex-col text-ink font-sans transition-colors duration-200">
            <Navbar theme={theme} onToggleTheme={toggleTheme} />
            <main className="flex-1">
              <Routes>
                <Route path="/" element={<Navigate to="/generate" replace />} />
                <Route path="/login" element={<Login />} />
                <Route path="/generate" element={<Generate />} />
                <Route path="/papers" element={<PaperHistory />} />
                <Route path="/papers/:id" element={<PaperReview />} />
                <Route path="/papers/:id/preview" element={<PaperPreview />} />
                <Route path="/bank" element={<QuestionBank />} />
                <Route path="*" element={<Navigate to="/generate" replace />} />
              </Routes>
            </main>
          </div>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
