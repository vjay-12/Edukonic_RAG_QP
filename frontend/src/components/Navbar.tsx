import React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Moon, Sun, Sparkles, BookOpen, FileText, Database, LogOut } from "lucide-react";

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
    <header className="flex items-center justify-between border-b border-line px-8 py-4 backdrop-blur-md sticky top-0 z-30 bg-[var(--surface)]">
      <Link to="/generate" className="flex items-center gap-3 no-underline text-inherit">
        <span className="display text-3xl font-normal tracking-tight text-white">
          Edkonic <span className="text-muted text-base font-sans font-normal">QP Studio</span>
        </span>
      </Link>

      <nav className="hidden md:flex items-center gap-6 text-sm font-medium">
        {navItems.map((item) => {
          const isActive = location.pathname.startsWith(item.path);
          const Icon = item.icon;
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-2 py-1.5 px-3 rounded-full transition-colors ${
                isActive
                  ? "bg-[var(--surface-hover)] text-white"
                  : "text-muted hover:text-white"
              }`}
            >
              <Icon size={16} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="flex items-center gap-3">
        <button
          className="btn btn-ghost !p-2.5 rounded-full"
          onClick={onToggleTheme}
          aria-label="Toggle dark/light theme"
        >
          {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
        </button>

        {isLoggedIn && (
          <button
            className="btn btn-ghost !p-2.5 text-muted hover:text-[var(--bad)] rounded-full"
            onClick={handleLogout}
            title="Sign out"
          >
            <LogOut size={17} />
          </button>
        )}
      </div>
    </header>
  );
};
