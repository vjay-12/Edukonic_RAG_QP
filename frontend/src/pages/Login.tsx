import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, ArrowRight, Lock, AlertCircle } from "lucide-react";
import { login } from "../api/client";

export const Login: React.FC = () => {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await login(password);
      localStorage.setItem("edkonic_token", res.token);
      navigate("/generate");
    } catch (err: any) {
      setError(err.message || "Invalid password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-80px)] items-center justify-center px-4 py-12">
      <div className="glass w-full max-w-md p-8 border border-line shadow-2xl relative">
        <div className="text-center mb-8">
          <span className="chip mb-4">
            <Sparkles size={13} className="text-blue-500 dark:text-blue-400" />
            <span>Teacher Authentication</span>
          </span>
          <h1 className="display text-4xl font-normal text-ink mt-2">
            Welcome to <span className="grad-blue">Edkonic</span>
          </h1>
          <p className="text-sm text-muted mt-2">
            Enter the school demo password to access the CBSE Question Paper Generator.
          </p>
        </div>

        {error && (
          <div className="mb-6 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-600 dark:text-rose-300 flex items-center gap-2">
            <AlertCircle size={15} className="shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <label className="text-xs font-medium text-muted flex items-center gap-1.5">
              <Lock size={13} />
              <span>Password</span>
            </label>
            <input
              type="password"
              className="field w-full text-sm"
              placeholder="Enter teacher password..."
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoFocus
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary w-full justify-center !py-3 text-sm mt-2"
          >
            {loading ? "Verifying..." : "Sign in to Studio"} <ArrowRight size={16} />
          </button>
        </form>

        <p className="text-center text-xs text-muted mt-6">
          Internal pilot for CBSE Class 10 Science · Powered by NCERT RAG
        </p>
      </div>
    </div>
  );
};
