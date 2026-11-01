import { useEffect, useId, useState } from "react";
import { api, type Category, type SearchParams, type Stock } from "./api";
import { PRESETS, presetRange, todayHkt, type Preset } from "./dates";

interface Props {
  busy: boolean;
  onSearch: (params: SearchParams) => void;
}

export function stockLabel(s: Stock): string {
  return `${s.code} ${s.name_en}${s.name_tc ? ` ${s.name_tc}` : ""}${s.active ? "" : " (delisted)"}`;
}

export function SearchForm({ busy, onSearch }: Props) {
  const today = todayHkt();
  const ids = { code: useId(), start: useId(), end: useId(), cat: useId(), kw: useId(), list: useId() };
  const [code, setCode] = useState("");
  const [stockId, setStockId] = useState<number | undefined>();
  const [open, setOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<Stock[]>([]);
  const [preset, setPreset] = useState<Preset>("30d");
  const [[start, end], setRange] = useState<[string, string]>(presetRange("30d", today));
  const [categories, setCategories] = useState<Category[]>([]);
  const [category, setCategory] = useState("");
  const [keyword, setKeyword] = useState("");

  useEffect(() => {
    api.categories().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    const q = code.trim();
    if (!q) return setSuggestions([]);
    const timer = setTimeout(() => api.stocks(q).then(setSuggestions).catch(() => setSuggestions([])), 200);
    return () => clearTimeout(timer);
  }, [code]);

  const choosePreset = (id: Preset) => {
    setPreset(id);
    if (id !== "custom") setRange(presetRange(id, today));
  };

  return (
    <form
      className="grid gap-5"
      onSubmit={(e) => {
        e.preventDefault();
        onSearch({
          stock_code: code,
          stock_id: stockId,
          start,
          end,
          categories: category ? [category] : [],
          keyword: keyword.trim() || undefined,
        });
      }}
    >
      <div
        className="relative"
        onBlur={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);
        }}
      >
        <label htmlFor={ids.code} className="block font-medium">
          Stock code or company name
        </label>
        <input
          id={ids.code}
          className="field mt-1 w-full"
          value={code}
          placeholder="For example 00700 or Tencent"
          autoComplete="off"
          inputMode="text"
          aria-controls={ids.list}
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
          }}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setCode(e.target.value);
            setStockId(undefined);
            setOpen(true);
          }}
        />
        {open && suggestions.length > 0 && stockId === undefined && (
          <ul
            id={ids.list}
            className="suggestions"
            aria-label="Matching companies"
            onMouseDown={(e) => e.preventDefault()}
          >
            {suggestions.map((s) => (
              <li key={s.stock_id}>
                <button
                  type="button"
                  onClick={() => {
                    setCode(s.code);
                    setStockId(s.stock_id);
                    setOpen(false);
                  }}
                >
                  <span className="font-medium">{s.code}</span> {s.name_en}{" "}
                  <span lang="zh-Hant">{s.name_tc}</span>
                  {!s.active && <span className="badge-muted">Delisted</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <fieldset>
        <legend className="font-medium">
          Publication dates <span className="text-muted font-normal">(Hong Kong time)</span>
        </legend>
        <div className="mt-1 flex flex-wrap gap-2" role="group" aria-label="Date presets">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              className="chip"
              aria-pressed={preset === p.id}
              onClick={() => choosePreset(p.id)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label htmlFor={ids.start}>From</label>
          <input
            id={ids.start}
            type="date"
            className="field"
            value={start}
            max={today}
            onChange={(e) => {
              setPreset("custom");
              setRange([e.target.value, end]);
            }}
          />
          <label htmlFor={ids.end}>to</label>
          <input
            id={ids.end}
            type="date"
            className="field"
            value={end}
            max={today}
            onChange={(e) => {
              setPreset("custom");
              setRange([start, e.target.value]);
            }}
          />
        </div>
      </fieldset>

      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <label htmlFor={ids.cat} className="block font-medium">
            Category
          </label>
          <select
            id={ids.cat}
            className="field mt-1 w-full"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name_en}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={ids.kw} className="block font-medium">
            Title contains <span className="text-muted font-normal">(optional)</span>
          </label>
          <input
            id={ids.kw}
            className="field mt-1 w-full"
            value={keyword}
            maxLength={100}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>
      </div>

      <div>
        <button type="submit" className="primary" disabled={busy || !code.trim()}>
          {busy ? "Searching…" : "Search announcements"}
        </button>
      </div>
    </form>
  );
}
