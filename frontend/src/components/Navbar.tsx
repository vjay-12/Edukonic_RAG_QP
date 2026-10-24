import React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Moon, Sun, Sparkles, FileText, Database, LogOut } from "lucide-react";

interface NavbarProps {
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ theme, onToggleTheme }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const isLoggedIn = !!localStorage.getItem("edkonic_token");

  const handleLogout = () => {
    localStorage.removeItem("edkonic_token");
    navigate("/login");
  };

  const navItems = [
    { label: "Generate", path: "/generate", icon: Sparkles },
    { label: "Papers", path: "/papers", icon: FileText },
    { label: "Question Bank", path: "/bank", icon: Database },
  ];

  return (
    <header className="flex items-center justify-between border-b border-line px-6 sm:px-8 py-3.5 backdrop-blur-md sticky top-0 z-30 bg-[var(--surface)] print:hidden transition-colors">
      <Link to="/generate" className="flex items-center gap-2.5 no-underline text-inherit group">
        {/* Edkonic Hexagon Brand Icon */}
        <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="text-blue-500">
            <path
              d="M12 2L20.66 7V17L12 22L3.34 17V7L12 2Z"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinejoin="round"
            />
            <circle cx="12" cy="12" r="3" fill="currentColor" fillOpacity="0.4" />
          </svg>
        </div>
        <span className="display text-2xl sm:text-3xl font-normal tracking-tight text-ink">
          Edkonic <span className="text-muted text-sm sm:text-base font-sans font-normal">QP Studio</span>
        </span>
      </Link>

      <nav className="hidden md:flex items-center gap-2 text-sm font-medium">
        {navItems.map((item) => {
          const isActive = location.pathname.startsWith(item.path);
          const Icon = item.icon;
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-2 py-1.5 px-3.5 rounded-full transition-colors ${
                isActive
                  ? "bg-[var(--surface-hover)] text-ink font-semibold shadow-xs"
                  : "text-muted hover:text-ink hover:bg-[var(--surface-hover)]"
              }`}
            >
              <Icon size={15} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="flex items-center gap-2.5">
        <button
          className="btn btn-ghost !p-2 rounded-full cursor-pointer hover:border-blue-500/40"
          onClick={onToggleTheme}
          aria-label="Toggle dark/light theme"
          title={`Switch to ${theme === "dark" ? "Light" : "Dark"} Mode`}
        >
          {theme === "dark" ? <Sun size={17} className="text-amber-300" /> : <Moon size={17} className="text-slate-700" />}
        </button>

        {isLoggedIn && (
          <button
            className="btn btn-ghost !p-2 text-muted hover:text-[var(--bad)] rounded-full cursor-pointer"
            onClick={handleLogout}
            title="Sign out"
          >
            <LogOut size={16} />
          </button>
        )}
      </div>
    </header>
  );
};
