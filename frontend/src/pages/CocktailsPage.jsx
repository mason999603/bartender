import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { MagnifyingGlass, X, Plus, Flask, ArrowsLeftRight, Trash } from "@phosphor-icons/react";
import { Toaster, toast } from "sonner";

const FLAVOUR_CHIPS = [
    "citrus", "bitter", "sweet", "smoky", "herbal", "fruity",
    "spicy", "floral", "warm", "tart", "creamy", "tropical",
    "nutty", "fizzy", "dry", "refreshing", "rich", "complex",
];

function CocktailModal({ cocktail, onClose, outOfStock = [], onDelete }) {
    const [subHints, setSubHints] = useState({}); // { ingredientName: [subs] }
    const [deleting, setDeleting] = useState(false);

    useEffect(() => {
        if (!cocktail) return;
        // For each ingredient in this spec that's 86'd, fetch subs.
        const need = (cocktail.ingredients || [])
            .map((i) => i.name)
            .filter((n) =>
                outOfStock.some((o) => o.toLowerCase().includes(n.toLowerCase()) || n.toLowerCase().includes(o.toLowerCase()))
            );
        if (need.length === 0) {
            setSubHints({});
            return;
        }
        let cancelled = false;
        Promise.all(
            need.map((n) =>
                api.get(`/substitutions/${encodeURIComponent(n)}`).then((r) => [n, r.data.subs]).catch(() => [n, null])
            )
        ).then((pairs) => {
            if (cancelled) return;
            const map = {};
            for (const [n, subs] of pairs) if (subs) map[n] = subs;
            setSubHints(map);
        });
        return () => {
            cancelled = true;
        };
    }, [cocktail, outOfStock]);

    if (!cocktail) return null;

    const isOut = (name) =>
        outOfStock.some((o) => o.toLowerCase().includes(name.toLowerCase()) || name.toLowerCase().includes(o.toLowerCase()));

    const handleDelete = async () => {
        if (!cocktail.is_custom) return;
        if (!window.confirm(`Remove '${cocktail.name}' from your library? This can't be undone.`)) return;
        setDeleting(true);
        try {
            await api.delete(`/cocktails/${cocktail.id}`);
            toast.success(`'${cocktail.name}' removed from your library`);
            onDelete?.(cocktail.id);
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Couldn't delete that one");
        } finally {
            setDeleting(false);
        }
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 fade-in"
            style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)" }}
            onClick={onClose}
            data-testid="cocktail-modal"
        >
            <div
                className="glass-strong rounded-2xl max-w-2xl w-full max-h-[85vh] overflow-y-auto p-8 relative"
                onClick={(e) => e.stopPropagation()}
            >
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 p-2 rounded-lg hover:bg-white/5"
                    data-testid="modal-close"
                >
                    <X size={20} />
                </button>
                {cocktail.is_custom && (
                    <button
                        onClick={handleDelete}
                        disabled={deleting}
                        className="absolute top-4 right-14 p-2 rounded-lg hover:bg-red-500/10 flex items-center gap-1.5 text-xs"
                        style={{ color: "#FCA5A5" }}
                        data-testid="modal-delete-cocktail"
                        title="Delete this custom spec"
                    >
                        <Trash size={16} />
                        {deleting ? "Removing…" : "Delete"}
                    </button>
                )}
                <div className="label-tiny mb-2">{cocktail.category}</div>
                <h2 className="font-serif text-4xl mb-4" style={{ color: "var(--accent)" }}>
                    {cocktail.name}
                </h2>
                <div className="flex gap-2 flex-wrap mb-6">
                    {cocktail.tags?.map((t) => (
                        <span key={t} className="badge">{t}</span>
                    ))}
                    {cocktail.abv_estimate > 0 && (
                        <span className="badge badge-amber">~{cocktail.abv_estimate}% ABV</span>
                    )}
                </div>

                <div className="grid sm:grid-cols-2 gap-6 mb-6">
                    <div>
                        <div className="label-tiny mb-2">Glassware</div>
                        <div className="text-base">{cocktail.glassware || "—"}</div>
                    </div>
                    <div>
                        <div className="label-tiny mb-2">Method</div>
                        <div className="text-base">{cocktail.method || "—"}</div>
                    </div>
                    <div>
                        <div className="label-tiny mb-2">Garnish</div>
                        <div className="text-base">{cocktail.garnish || "—"}</div>
                    </div>
                    <div>
                        <div className="label-tiny mb-2">Flavour</div>
                        <div className="text-base">{cocktail.flavor_profile?.join(", ") || "—"}</div>
                    </div>
                </div>

                <div className="mb-6">
                    <div className="label-tiny mb-3">Spec</div>
                    <div className="space-y-2">
                        {cocktail.ingredients?.map((ing, i) => {
                            const out = isOut(ing.name);
                            const subs = subHints[ing.name];
                            return (
                                <div key={i} className="border-b border-white/5 pb-2">
                                    <div className="flex items-baseline justify-between gap-4">
                                        <div>
                                            <span className={`font-medium ${out ? "line-through" : ""}`} style={out ? { color: "var(--text-secondary)" } : {}}>
                                                {ing.name}
                                            </span>
                                            {out && <span className="badge badge-danger ml-2">86'd</span>}
                                            {ing.notes && (
                                                <span className="ml-2 text-xs" style={{ color: "var(--text-secondary)" }}>
                                                    ({ing.notes})
                                                </span>
                                            )}
                                        </div>
                                        <div className="font-serif text-lg" style={{ color: "var(--accent)" }}>
                                            {ing.amount_ml > 0 ? `${ing.amount_ml} ml` : "—"}
                                        </div>
                                    </div>
                                    {out && subs && subs.length > 0 && (
                                        <div className="mt-2 ml-1 pl-3 border-l-2" style={{ borderColor: "var(--accent)" }} data-testid={`sub-hint-${i}`}>
                                            <div className="label-tiny mb-1 flex items-center gap-1">
                                                <ArrowsLeftRight size={11} weight="bold" /> Russell suggests
                                            </div>
                                            {subs.map((s, si) => (
                                                <div key={si} className="text-sm mb-1">
                                                    <span style={{ color: "var(--accent)" }}>{s.name}</span>
                                                    <span style={{ color: "var(--text-secondary)" }}> — {s.notes}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>

                {cocktail.instructions && (
                    <div>
                        <div className="label-tiny mb-2">Build</div>
                        <p style={{ color: "var(--text-primary)", lineHeight: 1.65 }}>{cocktail.instructions}</p>
                    </div>
                )}
            </div>
        </div>
    );
}

export default function CocktailsPage() {
    const [cocktails, setCocktails] = useState([]);
    const [search, setSearch] = useState("");
    const [flavourState, setFlavourState] = useState({}); // { citrus: 'include' | 'exclude' | undefined }
    const [selected, setSelected] = useState(null);
    const [loading, setLoading] = useState(true);
    const [showCreate, setShowCreate] = useState(false);
    const [outOfStock, setOutOfStock] = useState([]);

    // Cycle chip state: undefined → include → exclude → undefined
    const toggleChip = (flavour) => {
        setFlavourState((prev) => {
            const cur = prev[flavour];
            const next = cur === undefined ? "include" : cur === "include" ? "exclude" : undefined;
            const newState = { ...prev };
            if (next === undefined) delete newState[flavour];
            else newState[flavour] = next;
            return newState;
        });
    };

    const includes = Object.keys(flavourState).filter((k) => flavourState[k] === "include");
    const excludes = Object.keys(flavourState).filter((k) => flavourState[k] === "exclude");
    const flavourActive = includes.length > 0 || excludes.length > 0;

    const loadByName = async (q = "") => {
        setLoading(true);
        try {
            const res = await api.get("/cocktails", { params: { search: q } });
            setCocktails(res.data || []);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    const loadByFlavour = async () => {
        setLoading(true);
        try {
            const res = await api.post("/cocktails/by-flavour", { include: includes, exclude: excludes });
            // unwrap from { cocktail, ... } shape
            setCocktails((res.data || []).map((r) => r.cocktail));
        } catch (e) {
            console.error(e);
            toast.error("Flavour search failed");
        } finally {
            setLoading(false);
        }
    };

    // Initial load + load 86'd inventory once
    useEffect(() => {
        loadByName();
        api.get("/inventory").then((r) => {
            setOutOfStock((r.data || []).filter((i) => !i.in_stock).map((i) => i.name));
        });
    }, []);

    // React to either search OR flavour state
    useEffect(() => {
        const t = setTimeout(() => {
            if (flavourActive) loadByFlavour();
            else loadByName(search);
        }, 250);
        return () => clearTimeout(t);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [search, flavourState]);

    const clearFilters = () => {
        setFlavourState({});
        setSearch("");
    };

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
            <Toaster position="top-center" theme="dark" />
            <PageHeader
                eyebrow="Cocktail Library"
                title="The Book"
                subtitle="44 specs and counting. Tap a card for the full build. Search by name, or filter by flavour."
            >
                <button
                    onClick={() => setShowCreate(true)}
                    className="btn-amber flex items-center gap-2"
                    data-testid="add-cocktail-btn"
                >
                    <Plus size={16} weight="bold" /> Add Spec
                </button>
            </PageHeader>

            <div className="relative mb-4">
                <MagnifyingGlass
                    size={18}
                    className="absolute left-4 top-1/2 -translate-y-1/2 pointer-events-none"
                    style={{ color: "var(--text-secondary)", zIndex: 1 }}
                />
                <input
                    className="input-dark pl-12"
                    placeholder={flavourActive ? "Search disabled while flavour filter active" : "Search by name…"}
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    disabled={flavourActive}
                    data-testid="cocktail-search"
                />
            </div>

            <div className="mb-6">
                <div className="flex items-center justify-between mb-2">
                    <div className="label-tiny">Flavour filter — tap to include, again to exclude</div>
                    {flavourActive && (
                        <button onClick={clearFilters} className="text-xs flex items-center gap-1" style={{ color: "var(--text-secondary)" }} data-testid="clear-flavour-filters">
                            <X size={12} /> Clear
                        </button>
                    )}
                </div>
                <div className="flex flex-wrap gap-2">
                    {FLAVOUR_CHIPS.map((f) => {
                        const state = flavourState[f];
                        const cls =
                            state === "include"
                                ? "badge-amber"
                                : state === "exclude"
                                ? "badge-danger"
                                : "";
                        return (
                            <button
                                key={f}
                                onClick={() => toggleChip(f)}
                                className={`badge ${cls}`}
                                style={{
                                    cursor: "pointer",
                                    textDecoration: state === "exclude" ? "line-through" : "none",
                                }}
                                data-testid={`flavour-chip-${f}`}
                            >
                                {state === "exclude" ? "− " : state === "include" ? "+ " : ""}
                                {f}
                            </button>
                        );
                    })}
                </div>
            </div>

            {loading ? (
                <div className="text-center py-16" style={{ color: "var(--text-secondary)" }}>Polishing glassware…</div>
            ) : cocktails.length === 0 ? (
                <div className="text-center py-16" style={{ color: "var(--text-secondary)" }}>
                    {flavourActive ? "No drinks match those flavours. Try loosening up." : "No drinks match. Try a different search."}
                </div>
            ) : (
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
                    {cocktails.map((c) => (
                        <button
                            key={c.id}
                            onClick={() => setSelected(c)}
                            className="tool-card text-left"
                            data-testid={`cocktail-card-${c.name.toLowerCase().replace(/\s+/g, "-")}`}
                        >
                            <div className="flex items-start justify-between gap-3 mb-3">
                                <h3 className="font-serif text-2xl" style={{ color: "var(--text-primary)" }}>
                                    {c.name}
                                </h3>
                                {c.is_custom && <span className="badge badge-amber">Custom</span>}
                            </div>
                            <div className="label-tiny mb-2">{c.category}</div>
                            <p className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
                                {c.flavor_profile?.slice(0, 4).join(" · ")}
                            </p>
                            <div className="flex items-center justify-between text-xs" style={{ color: "var(--text-muted)" }}>
                                <span>{c.ingredients?.length || 0} ingredients</span>
                                {c.abv_estimate > 0 && <span>~{c.abv_estimate}% ABV</span>}
                            </div>
                        </button>
                    ))}
                </div>
            )}

            <CocktailModal
                cocktail={selected}
                onClose={() => setSelected(null)}
                outOfStock={outOfStock}
                onDelete={(id) => {
                    setCocktails((prev) => prev.filter((c) => c.id !== id));
                    setSelected(null);
                }}
            />
            {showCreate && (
                <CreateCocktailModal
                    onClose={() => setShowCreate(false)}
                    onCreated={() => {
                        setShowCreate(false);
                        toast.success("Spec saved");
                        loadByName(search);
                    }}
                />
            )}
        </div>
    );
}

function CreateCocktailModal({ onClose, onCreated }) {
    const [name, setName] = useState("");
    const [method, setMethod] = useState("");
    const [glassware, setGlassware] = useState("");
    const [garnish, setGarnish] = useState("");
    const [instructions, setInstructions] = useState("");
    const [ingredients, setIngredients] = useState([{ name: "", amount_ml: 0, notes: "" }]);
    const [saving, setSaving] = useState(false);

    const addRow = () => setIngredients([...ingredients, { name: "", amount_ml: 0, notes: "" }]);
    const updateRow = (i, k, v) => {
        const next = [...ingredients];
        next[i] = { ...next[i], [k]: k === "amount_ml" ? parseFloat(v) || 0 : v };
        setIngredients(next);
    };
    const removeRow = (i) => setIngredients(ingredients.filter((_, idx) => idx !== i));

    const submit = async () => {
        if (!name.trim()) return toast.error("Name required");
        const cleaned = ingredients.filter((x) => x.name.trim());
        if (cleaned.length === 0) return toast.error("At least one ingredient");
        setSaving(true);
        try {
            await api.post("/cocktails", {
                name,
                method,
                glassware,
                garnish,
                instructions,
                ingredients: cleaned,
                category: "custom",
                flavor_profile: [],
                tags: ["custom"],
                abv_estimate: 0,
            });
            onCreated();
        } catch {
            toast.error("Couldn't save");
        } finally {
            setSaving(false);
        }
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 fade-in"
            style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)" }}
            onClick={onClose}
        >
            <div
                className="glass-strong rounded-2xl max-w-2xl w-full max-h-[85vh] overflow-y-auto p-8"
                onClick={(e) => e.stopPropagation()}
                data-testid="create-cocktail-modal"
            >
                <div className="flex items-center justify-between mb-6">
                    <h2 className="font-serif text-3xl" style={{ color: "var(--accent)" }}>
                        New Spec
                    </h2>
                    <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/5" data-testid="create-close">
                        <X size={20} />
                    </button>
                </div>

                <div className="space-y-4">
                    <div>
                        <div className="label-tiny mb-1">Name</div>
                        <input className="input-dark" value={name} onChange={(e) => setName(e.target.value)} data-testid="cc-name" />
                    </div>
                    <div className="grid sm:grid-cols-2 gap-4">
                        <div>
                            <div className="label-tiny mb-1">Glassware</div>
                            <input className="input-dark" value={glassware} onChange={(e) => setGlassware(e.target.value)} data-testid="cc-glassware" />
                        </div>
                        <div>
                            <div className="label-tiny mb-1">Method</div>
                            <input className="input-dark" value={method} onChange={(e) => setMethod(e.target.value)} data-testid="cc-method" />
                        </div>
                    </div>
                    <div>
                        <div className="label-tiny mb-1">Garnish</div>
                        <input className="input-dark" value={garnish} onChange={(e) => setGarnish(e.target.value)} data-testid="cc-garnish" />
                    </div>

                    <div>
                        <div className="label-tiny mb-2">Ingredients</div>
                        {ingredients.map((ing, i) => (
                            <div key={i} className="grid grid-cols-12 gap-2 mb-2">
                                <input
                                    className="input-dark col-span-5"
                                    placeholder="Name"
                                    value={ing.name}
                                    onChange={(e) => updateRow(i, "name", e.target.value)}
                                    data-testid={`cc-ing-name-${i}`}
                                />
                                <input
                                    type="number"
                                    className="input-dark col-span-2"
                                    placeholder="ml"
                                    value={ing.amount_ml || ""}
                                    onChange={(e) => updateRow(i, "amount_ml", e.target.value)}
                                />
                                <input
                                    className="input-dark col-span-4"
                                    placeholder="Notes"
                                    value={ing.notes}
                                    onChange={(e) => updateRow(i, "notes", e.target.value)}
                                />
                                <button onClick={() => removeRow(i)} className="btn-ghost col-span-1 px-0">
                                    <X size={16} />
                                </button>
                            </div>
                        ))}
                        <button onClick={addRow} className="btn-ghost text-sm" data-testid="cc-add-row">
                            <Plus size={14} className="inline mr-1" /> Add ingredient
                        </button>
                    </div>

                    <div>
                        <div className="label-tiny mb-1">Build / Method notes</div>
                        <textarea
                            className="input-dark"
                            rows={3}
                            value={instructions}
                            onChange={(e) => setInstructions(e.target.value)}
                            data-testid="cc-instructions"
                        />
                    </div>

                    <div className="flex justify-end gap-2 pt-2">
                        <button onClick={onClose} className="btn-ghost">Cancel</button>
                        <button onClick={submit} disabled={saving} className="btn-amber" data-testid="cc-save">
                            <Flask size={16} weight="bold" className="inline mr-2" />
                            {saving ? "Saving…" : "Save spec"}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
