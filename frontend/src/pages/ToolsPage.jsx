import React, { useState, useEffect } from "react";
import { api } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Toaster, toast } from "sonner";
import { Warning, Flask, Calculator, CurrencyDollar, MagicWand, Plus, X, CheckCircle, ArrowsLeftRight } from "@phosphor-icons/react";

const TABS = [
    { key: "make", label: "What Can I Make", icon: MagicWand },
    { key: "clash", label: "Clash Check", icon: Warning },
    { key: "subs", label: "Subs", icon: ArrowsLeftRight },
    { key: "abv", label: "ABV", icon: Flask },
    { key: "batch", label: "Batching", icon: Calculator },
    { key: "cost", label: "Cost", icon: CurrencyDollar },
];

export default function ToolsPage() {
    const [tab, setTab] = useState("make");
    return (
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
            <Toaster position="top-center" theme="dark" />
            <PageHeader eyebrow="Bartender's tools" title="Behind the stick" subtitle="Quick maths and chemistry checks for service." />

            <div className="flex flex-wrap gap-2 mb-8 border-b border-white/5 pb-3">
                {TABS.map(({ key, label, icon: Icon }) => (
                    <button
                        key={key}
                        onClick={() => setTab(key)}
                        className={`nav-link ${tab === key ? "active" : ""}`}
                        data-testid={`tool-tab-${key}`}
                    >
                        <Icon size={16} weight="bold" />
                        {label}
                    </button>
                ))}
            </div>

            <div className="fade-in" key={tab}>
                {tab === "make" && <WhatCanIMake />}
                {tab === "clash" && <ClashCheck />}
                {tab === "subs" && <SubsLookup />}
                {tab === "abv" && <AbvCalc />}
                {tab === "batch" && <BatchCalc />}
                {tab === "cost" && <CostCalc />}
            </div>
        </div>
    );
}

function SubsLookup() {
    const [query, setQuery] = useState("");
    const [result, setResult] = useState(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [allSubs, setAllSubs] = useState([]);

    useEffect(() => {
        api.get("/substitutions").then((r) => setAllSubs(r.data || []));
    }, []);

    const lookup = async (name) => {
        const q = (name ?? query).trim();
        if (!q) return;
        setLoading(true);
        setError("");
        setResult(null);
        try {
            const res = await api.get(`/substitutions/${encodeURIComponent(q)}`);
            setResult(res.data);
        } catch (e) {
            setError(e?.response?.data?.detail || "No subs on file for that one. Ask Sheldon in chat — he'll improvise.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="grid lg:grid-cols-2 gap-6">
            <div className="tool-card">
                <div className="label-tiny mb-3">Look up swaps for an ingredient</div>
                <div className="flex gap-2 mb-4">
                    <input
                        className="input-dark flex-1"
                        placeholder="e.g. Cointreau"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && lookup()}
                        data-testid="subs-input"
                    />
                    <button onClick={() => lookup()} className="btn-amber" data-testid="subs-lookup">
                        Find swaps
                    </button>
                </div>
                <div className="label-tiny mb-2 mt-6">Browse all on file</div>
                <div className="flex flex-wrap gap-2">
                    {allSubs.map((s) => (
                        <button
                            key={s.ingredient}
                            onClick={() => {
                                setQuery(s.ingredient);
                                lookup(s.ingredient);
                            }}
                            className="badge"
                            style={{ cursor: "pointer" }}
                            data-testid={`subs-quick-${s.ingredient.toLowerCase().replace(/\s+/g, "-")}`}
                        >
                            {s.ingredient}
                        </button>
                    ))}
                </div>
            </div>
            <div>
                <div className="label-tiny mb-3">Suggestions</div>
                {loading && <div style={{ color: "var(--text-secondary)" }}>Thinking…</div>}
                {error && (
                    <div className="tool-card text-sm" style={{ color: "var(--text-secondary)" }}>
                        {error}
                    </div>
                )}
                {result && (
                    <div className="tool-card" data-testid="subs-result">
                        <div className="label-tiny mb-1">In place of</div>
                        <h3 className="font-serif text-2xl mb-4" style={{ color: "var(--accent)" }}>
                            {result.ingredient}
                        </h3>
                        <div className="space-y-3">
                            {result.subs.map((s, i) => (
                                <div key={i} className="border-l-2 pl-3" style={{ borderColor: "var(--accent)" }}>
                                    <div className="font-medium" style={{ color: "var(--text-primary)" }}>
                                        {s.name}
                                    </div>
                                    <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                                        {s.notes}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
                {!loading && !error && !result && (
                    <div className="tool-card text-sm" style={{ color: "var(--text-secondary)" }}>
                        Hit a tag or type an ingredient. Try Cointreau, Lime Juice, or Sweet Vermouth.
                    </div>
                )}
            </div>
        </div>
    );
}

function IngredientList({ items, setItems, placeholder = "e.g. Bourbon", testidPrefix = "ing" }) {
    const [val, setVal] = useState("");
    const add = () => {
        if (!val.trim()) return;
        setItems([...items, val.trim()]);
        setVal("");
    };
    return (
        <div>
            <div className="flex gap-2 mb-3">
                <input
                    className="input-dark flex-1"
                    placeholder={placeholder}
                    value={val}
                    onChange={(e) => setVal(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && add()}
                    data-testid={`${testidPrefix}-input`}
                />
                <button onClick={add} className="btn-amber" data-testid={`${testidPrefix}-add`}>
                    <Plus size={16} weight="bold" />
                </button>
            </div>
            <div className="flex flex-wrap gap-2">
                {items.map((it, i) => (
                    <span key={i} className="badge badge-amber flex items-center gap-2">
                        {it}
                        <button onClick={() => setItems(items.filter((_, idx) => idx !== i))}>
                            <X size={12} />
                        </button>
                    </span>
                ))}
            </div>
        </div>
    );
}

function WhatCanIMake() {
    const [items, setItems] = useState([]);
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);

    const search = async () => {
        if (items.length === 0) return toast.error("Add some ingredients first");
        setLoading(true);
        try {
            const res = await api.post("/cocktails/search-by-ingredients", { ingredients: items });
            setResults(res.data || []);
        } catch {
            toast.error("Search failed");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="grid lg:grid-cols-2 gap-6">
            <div className="tool-card">
                <div className="label-tiny mb-3">Your ingredients</div>
                <IngredientList items={items} setItems={setItems} testidPrefix="make-ing" />
                <button onClick={search} className="btn-amber mt-6" data-testid="make-search">
                    Show me what works
                </button>
            </div>
            <div>
                <div className="label-tiny mb-3">Matches</div>
                {loading && <div style={{ color: "var(--text-secondary)" }}>Searching the book…</div>}
                {!loading && results.length === 0 && (
                    <div className="tool-card text-sm" style={{ color: "var(--text-secondary)" }}>
                        Results show up here. Try: gin, lime juice, simple syrup.
                    </div>
                )}
                <div className="space-y-3">
                    {results.map((r, i) => (
                        <div key={i} className="tool-card" data-testid={`make-result-${i}`}>
                            <div className="flex items-baseline justify-between mb-2">
                                <h3 className="font-serif text-2xl" style={{ color: "var(--accent)" }}>
                                    {r.cocktail.name}
                                </h3>
                                <span className="badge">{Math.round(r.match_ratio * 100)}% match</span>
                            </div>
                            <div className="text-xs mb-2" style={{ color: "var(--text-secondary)" }}>
                                {r.cocktail.ingredients.map((x) => x.name).join(" · ")}
                            </div>
                            {r.missing.length > 0 && (
                                <div className="text-xs" style={{ color: "var(--accent)" }}>
                                    Missing: {r.missing.join(", ")}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

function ClashCheck() {
    const [items, setItems] = useState([]);
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);

    const run = async () => {
        if (items.length < 2) return toast.error("Add at least two ingredients");
        setLoading(true);
        try {
            const res = await api.post("/tools/compatibility", { ingredients: items });
            setResult(res.data);
        } catch {
            toast.error("Check failed");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="grid lg:grid-cols-2 gap-6">
            <div className="tool-card">
                <div className="label-tiny mb-3">Ingredients to check</div>
                <IngredientList
                    items={items}
                    setItems={setItems}
                    placeholder="e.g. Baileys Irish Cream"
                    testidPrefix="clash-ing"
                />
                <button onClick={run} className="btn-amber mt-6" data-testid="clash-run">
                    Check chemistry
                </button>
            </div>
            <div>
                <div className="label-tiny mb-3">Verdict</div>
                {loading && <div style={{ color: "var(--text-secondary)" }}>Thinking…</div>}
                {!loading && !result && (
                    <div className="tool-card text-sm" style={{ color: "var(--text-secondary)" }}>
                        Try: Baileys Irish Cream + Lime Juice 👀
                    </div>
                )}
                {result && (
                    <div className="tool-card">
                        {result.verdict === "ok" ? (
                            <div className="flex items-center gap-3 mb-3">
                                <CheckCircle size={24} weight="fill" style={{ color: "var(--accent)" }} />
                                <span className="font-serif text-2xl" style={{ color: "var(--text-primary)" }}>
                                    All good
                                </span>
                            </div>
                        ) : (
                            <div className="flex items-center gap-3 mb-3">
                                <Warning size={24} weight="fill" style={{ color: "#FCA5A5" }} />
                                <span className="font-serif text-2xl" style={{ color: "#FCA5A5" }}>
                                    {result.verdict === "fatal" ? "Won't work" : "Heads up"}
                                </span>
                            </div>
                        )}
                        {result.warnings?.map((w, i) => (
                            <div key={i} className="border-t border-white/5 pt-3 mt-3">
                                <div className="flex items-center gap-2 mb-1">
                                    <span className="font-medium">{w.a}</span>
                                    <span style={{ color: "var(--text-secondary)" }}>+</span>
                                    <span className="font-medium">{w.b}</span>
                                    <span className={`badge ${w.severity === "fatal" ? "badge-danger" : "badge-amber"}`}>
                                        {w.severity}
                                    </span>
                                </div>
                                <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
                                    {w.reason}
                                </p>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

function AbvCalc() {
    const [rows, setRows] = useState([
        { name: "Bourbon", amount_ml: 60, abv: 45 },
        { name: "Sweet Vermouth", amount_ml: 30, abv: 16 },
    ]);
    const [dilution, setDilution] = useState(25);
    const [result, setResult] = useState(null);

    const update = (i, k, v) => {
        const next = [...rows];
        next[i] = { ...next[i], [k]: k === "name" ? v : parseFloat(v) || 0 };
        setRows(next);
    };

    const run = async () => {
        try {
            const res = await api.post("/tools/abv", {
                ingredients: rows.filter((r) => r.name && r.amount_ml > 0),
                dilution_ml: dilution,
            });
            setResult(res.data);
        } catch {
            toast.error("Calc failed");
        }
    };

    return (
        <div className="grid lg:grid-cols-2 gap-6">
            <div className="tool-card">
                <div className="label-tiny mb-3">Ingredients (ml + % ABV)</div>
                {rows.map((r, i) => (
                    <div key={i} className="grid grid-cols-12 gap-2 mb-2">
                        <input
                            className="input-dark col-span-6"
                            value={r.name}
                            onChange={(e) => update(i, "name", e.target.value)}
                            placeholder="Ingredient"
                        />
                        <input
                            type="number"
                            className="input-dark col-span-3"
                            value={r.amount_ml || ""}
                            onChange={(e) => update(i, "amount_ml", e.target.value)}
                            placeholder="ml"
                        />
                        <input
                            type="number"
                            className="input-dark col-span-2"
                            value={r.abv || ""}
                            onChange={(e) => update(i, "abv", e.target.value)}
                            placeholder="%"
                        />
                        <button
                            onClick={() => setRows(rows.filter((_, idx) => idx !== i))}
                            className="btn-ghost col-span-1 px-0"
                        >
                            <X size={14} />
                        </button>
                    </div>
                ))}
                <button
                    onClick={() => setRows([...rows, { name: "", amount_ml: 0, abv: 0 }])}
                    className="btn-ghost text-sm mb-4"
                >
                    <Plus size={14} className="inline mr-1" /> Add ingredient
                </button>

                <div className="mt-2">
                    <div className="label-tiny mb-1">Dilution (ml of water/ice melt)</div>
                    <input
                        type="number"
                        className="input-dark"
                        value={dilution}
                        onChange={(e) => setDilution(parseFloat(e.target.value) || 0)}
                    />
                    <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                        Rule of thumb: ~25 ml shaken, ~20 ml stirred for a single drink.
                    </p>
                </div>
                <button onClick={run} className="btn-amber mt-6" data-testid="abv-run">Calculate</button>
            </div>
            <div>
                <div className="label-tiny mb-3">Result</div>
                {result ? (
                    <div className="tool-card">
                        <div className="text-center py-4">
                            <div className="font-serif font-light" style={{ fontSize: "5rem", color: "var(--accent)", lineHeight: 1 }}>
                                {result.abv}%
                            </div>
                            <div className="label-tiny mt-2">Final ABV</div>
                        </div>
                        <div className="grid grid-cols-2 gap-4 border-t border-white/5 pt-4 mt-4 text-sm">
                            <div>
                                <div className="label-tiny">Volume</div>
                                <div>{result.total_volume_ml} ml</div>
                            </div>
                            <div>
                                <div className="label-tiny">Pure alcohol</div>
                                <div>{result.alcohol_ml} ml</div>
                            </div>
                            <div>
                                <div className="label-tiny">Std drinks (AU)</div>
                                <div>{result.standard_drinks_au}</div>
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className="tool-card text-sm" style={{ color: "var(--text-secondary)" }}>
                        Hit calculate to see the math.
                    </div>
                )}
            </div>
        </div>
    );
}

function BatchCalc() {
    const [cocktails, setCocktails] = useState([]);
    const [selectedId, setSelectedId] = useState("");
    const [servings, setServings] = useState(20);
    const [dilution, setDilution] = useState(22);
    const [result, setResult] = useState(null);

    useEffect(() => {
        api.get("/cocktails").then((r) => setCocktails(r.data || []));
    }, []);

    const run = async () => {
        if (!selectedId) return toast.error("Pick a cocktail");
        try {
            const res = await api.post("/tools/batch", {
                cocktail_id: selectedId,
                servings,
                dilution_pct: dilution,
            });
            setResult(res.data);
        } catch {
            toast.error("Batch failed");
        }
    };

    return (
        <div className="grid lg:grid-cols-2 gap-6">
            <div className="tool-card">
                <div className="label-tiny mb-3">Pick a cocktail</div>
                <select
                    className="input-dark mb-4"
                    value={selectedId}
                    onChange={(e) => setSelectedId(e.target.value)}
                    data-testid="batch-cocktail-select"
                >
                    <option value="">— Select —</option>
                    {cocktails.map((c) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                </select>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <div className="label-tiny mb-1">Servings</div>
                        <input
                            type="number"
                            className="input-dark"
                            value={servings}
                            onChange={(e) => setServings(parseInt(e.target.value) || 1)}
                            data-testid="batch-servings"
                        />
                    </div>
                    <div>
                        <div className="label-tiny mb-1">Dilution %</div>
                        <input
                            type="number"
                            className="input-dark"
                            value={dilution}
                            onChange={(e) => setDilution(parseFloat(e.target.value) || 0)}
                        />
                    </div>
                </div>
                <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
                    20-25% water mimics stir dilution. 0% for shaken (serve to order).
                </p>
                <button onClick={run} className="btn-amber mt-6" data-testid="batch-run">
                    Scale it up
                </button>
            </div>
            <div>
                <div className="label-tiny mb-3">Recipe x{servings}</div>
                {result ? (
                    <div className="tool-card">
                        {result.scaled_ingredients.map((ing, i) => (
                            <div key={i} className="flex items-baseline justify-between border-b border-white/5 py-2">
                                <span>{ing.name}</span>
                                <span className="font-serif text-lg" style={{ color: "var(--accent)" }}>
                                    {ing.amount_ml >= 1000 ? `${(ing.amount_ml / 1000).toFixed(2)} L` : `${ing.amount_ml} ml`}
                                </span>
                            </div>
                        ))}
                        {result.added_dilution_water_ml > 0 && (
                            <div className="flex items-baseline justify-between py-2 mt-1">
                                <span style={{ color: "var(--text-secondary)" }}>+ Water (dilution)</span>
                                <span className="font-serif text-lg" style={{ color: "var(--accent)" }}>
                                    {result.added_dilution_water_ml} ml
                                </span>
                            </div>
                        )}
                        <div className="flex items-baseline justify-between border-t border-white/10 pt-3 mt-3">
                            <span className="font-medium">Total</span>
                            <span className="font-serif text-2xl" style={{ color: "var(--accent)" }}>
                                {result.total_volume_ml >= 1000
                                    ? `${(result.total_volume_ml / 1000).toFixed(2)} L`
                                    : `${result.total_volume_ml} ml`}
                            </span>
                        </div>
                        <p className="text-xs mt-3" style={{ color: "var(--text-muted)" }}>
                            {result.tip}
                        </p>
                    </div>
                ) : (
                    <div className="tool-card text-sm" style={{ color: "var(--text-secondary)" }}>
                        Pick a cocktail and hit scale.
                    </div>
                )}
            </div>
        </div>
    );
}

function CostCalc() {
    const [rows, setRows] = useState([
        { name: "Bourbon", amount_ml: 60, price_per_litre: 60 },
        { name: "Sweet Vermouth", amount_ml: 30, price_per_litre: 25 },
    ]);
    const [extra, setExtra] = useState(0.5);
    const [result, setResult] = useState(null);

    const update = (i, k, v) => {
        const next = [...rows];
        next[i] = { ...next[i], [k]: k === "name" ? v : parseFloat(v) || 0 };
        setRows(next);
    };

    const run = async () => {
        try {
            const res = await api.post("/tools/cost", {
                ingredients: rows.filter((r) => r.name && r.amount_ml > 0),
                extra_cost: extra,
            });
            setResult(res.data);
        } catch {
            toast.error("Cost calc failed");
        }
    };

    return (
        <div className="grid lg:grid-cols-2 gap-6">
            <div className="tool-card">
                <div className="label-tiny mb-3">Ingredients (ml + $/litre)</div>
                {rows.map((r, i) => (
                    <div key={i} className="grid grid-cols-12 gap-2 mb-2">
                        <input
                            className="input-dark col-span-5"
                            value={r.name}
                            onChange={(e) => update(i, "name", e.target.value)}
                            placeholder="Ingredient"
                        />
                        <input
                            type="number"
                            className="input-dark col-span-3"
                            value={r.amount_ml || ""}
                            onChange={(e) => update(i, "amount_ml", e.target.value)}
                            placeholder="ml"
                        />
                        <input
                            type="number"
                            className="input-dark col-span-3"
                            value={r.price_per_litre || ""}
                            onChange={(e) => update(i, "price_per_litre", e.target.value)}
                            placeholder="$/L"
                        />
                        <button
                            onClick={() => setRows(rows.filter((_, idx) => idx !== i))}
                            className="btn-ghost col-span-1 px-0"
                        >
                            <X size={14} />
                        </button>
                    </div>
                ))}
                <button
                    onClick={() => setRows([...rows, { name: "", amount_ml: 0, price_per_litre: 0 }])}
                    className="btn-ghost text-sm mb-4"
                >
                    <Plus size={14} className="inline mr-1" /> Add ingredient
                </button>
                <div>
                    <div className="label-tiny mb-1">Extra cost (garnish, ice, etc.)</div>
                    <input
                        type="number"
                        step="0.1"
                        className="input-dark"
                        value={extra}
                        onChange={(e) => setExtra(parseFloat(e.target.value) || 0)}
                    />
                </div>
                <button onClick={run} className="btn-amber mt-6" data-testid="cost-run">Calculate</button>
            </div>
            <div>
                <div className="label-tiny mb-3">Pour cost</div>
                {result ? (
                    <div className="tool-card">
                        <div className="text-center py-2">
                            <div className="font-serif font-light" style={{ fontSize: "3.5rem", color: "var(--accent)", lineHeight: 1 }}>
                                ${result.total_cost}
                            </div>
                            <div className="label-tiny mt-1">Cost per cocktail</div>
                        </div>
                        <div className="grid grid-cols-2 gap-3 mt-4 border-t border-white/5 pt-4">
                            <div className="text-center">
                                <div className="label-tiny">Menu @ 4x</div>
                                <div className="font-serif text-2xl" style={{ color: "var(--text-primary)" }}>
                                    ${result.suggested_menu_price_4x}
                                </div>
                            </div>
                            <div className="text-center">
                                <div className="label-tiny">Menu @ 5x</div>
                                <div className="font-serif text-2xl" style={{ color: "var(--text-primary)" }}>
                                    ${result.suggested_menu_price_5x}
                                </div>
                            </div>
                        </div>
                        <p className="text-xs mt-3" style={{ color: "var(--text-muted)" }}>{result.note}</p>
                    </div>
                ) : (
                    <div className="tool-card text-sm" style={{ color: "var(--text-secondary)" }}>
                        Hit calculate.
                    </div>
                )}
            </div>
        </div>
    );
}
