import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { MagnifyingGlass, X, Plus, Flask } from "@phosphor-icons/react";
import { Toaster, toast } from "sonner";

function CocktailModal({ cocktail, onClose }) {
    if (!cocktail) return null;
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
                        {cocktail.ingredients?.map((ing, i) => (
                            <div key={i} className="flex items-baseline justify-between gap-4 border-b border-white/5 pb-2">
                                <div>
                                    <span className="font-medium">{ing.name}</span>
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
                        ))}
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
    const [selected, setSelected] = useState(null);
    const [loading, setLoading] = useState(true);
    const [showCreate, setShowCreate] = useState(false);

    const load = async (q = "") => {
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

    useEffect(() => {
        load();
    }, []);

    useEffect(() => {
        const t = setTimeout(() => load(search), 250);
        return () => clearTimeout(t);
    }, [search]);

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
            <Toaster position="top-center" theme="dark" />
            <PageHeader
                eyebrow="Cocktail Library"
                title="The Book"
                subtitle="Classics, modern classics, your own specs. Tap a card for the full build."
            >
                <button
                    onClick={() => setShowCreate(true)}
                    className="btn-amber flex items-center gap-2"
                    data-testid="add-cocktail-btn"
                >
                    <Plus size={16} weight="bold" /> Add Spec
                </button>
            </PageHeader>

            <div className="relative mb-6">
                <MagnifyingGlass
                    size={18}
                    className="absolute left-4 top-1/2 -translate-y-1/2 pointer-events-none"
                    style={{ color: "var(--text-secondary)", zIndex: 1 }}
                />
                <input
                    className="input-dark pl-12"
                    placeholder="Search by name…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    data-testid="cocktail-search"
                />
            </div>

            {loading ? (
                <div className="text-center py-16" style={{ color: "var(--text-secondary)" }}>Polishing glassware…</div>
            ) : cocktails.length === 0 ? (
                <div className="text-center py-16" style={{ color: "var(--text-secondary)" }}>
                    No drinks match. Try a different search.
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

            <CocktailModal cocktail={selected} onClose={() => setSelected(null)} />
            {showCreate && (
                <CreateCocktailModal
                    onClose={() => setShowCreate(false)}
                    onCreated={() => {
                        setShowCreate(false);
                        toast.success("Spec saved");
                        load(search);
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
