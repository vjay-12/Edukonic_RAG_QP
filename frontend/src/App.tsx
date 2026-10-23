import React, { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { Navbar } from "./components/Navbar";
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

export default function App() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
  };

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="bg-glow min-h-screen flex flex-col text-inherit font-sans">
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
      </BrowserRouter>
    </QueryClientProvider>
  );
}
