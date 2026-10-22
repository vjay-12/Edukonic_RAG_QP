import { useState } from "react";
import { Sparkles, Moon, Sun, ArrowRight } from "lucide-react";

// Placeholder shell showing the theme. Real pages (Generate, Review, Papers, Bank) replace this.
export default function App() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    setTheme(next);
  };

  return (
    <div className="bg-glow min-h-full">
      <header className="flex items-center justify-between border-b border-line px-8 py-5">
        <div className="display text-3xl">Edkonic <span className="text-muted text-lg font-sans">QP Studio</span></div>
        <nav className="hidden gap-8 text-muted md:flex">
          <a>Generate</a><a>Papers</a><a>Question bank</a>
        </nav>
        <button className="btn btn-ghost !p-3" onClick={toggle} aria-label="Toggle theme">
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
        </button>
      </header>

      <main className="mx-auto max-w-5xl px-8 py-16">
        <span className="chip"><Sparkles size={14} /> New · AI question paper generator</span>
        <h1 className="display mt-8 text-6xl md:text-7xl">
          Board-ready papers, <span className="grad-blue">grounded</span> in your <span className="grad-pink">NCERT</span> books.
        </h1>
        <p className="mt-6 max-w-xl text-lg text-muted">
          Pick chapters, set marks and difficulty, and generate a paper with answer key and source pages.
        </p>
        <div className="mt-10 flex gap-4">
          <button className="btn btn-primary">Generate paper <ArrowRight size={18} /></button>
          <button className="btn btn-ghost">View papers</button>
        </div>

        <section className="glass mt-14 grid gap-5 p-6 md:grid-cols-2">
          <label className="grid gap-2 text-sm text-muted">Paper title<input className="field" defaultValue="Unit Test 1 - Science" /></label>
          <label className="grid gap-2 text-sm text-muted">Total marks<input className="field" defaultValue="25" /></label>
          <div className="md:col-span-2">
            <div className="mb-2 flex justify-between text-sm text-muted"><span>Generating Section C…</span><span>62%</span></div>
            <div className="bar"><i style={{ width: "62%" }} /></div>
          </div>
          <div className="flex gap-2 md:col-span-2">
            <span className="chip chip-ok">Validated</span>
            <span className="chip chip-warn">Needs review</span>
            <span className="chip chip-bad">Failed check</span>
            <span className="chip">NCERT Science 10 · p.178</span>
          </div>
        </section>
      </main>
    </div>
  );
}
