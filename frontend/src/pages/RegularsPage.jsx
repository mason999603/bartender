import React, { useState, useEffect } from "react";
import { api } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Toaster, toast } from "sonner";
import { Plus, Trash, User } from "@phosphor-icons/react";

export default function RegularsPage() {
    const [regulars, setRegulars] = useState([]);
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState({ name: "", likes: "", dislikes: "", favourite_cocktails: "", notes: "" });

    const load = async () => {
        const res = await api.get("/regulars");
        setRegulars(res.data || []);
    };

    useEffect(() => {
        load();
    }, []);

    const save = async () => {
        if (!form.name.trim()) return toast.error("Name required");
        try {
            await api.post("/regulars", {
                name: form.name,
                likes: form.likes.split(",").map((s) => s.trim()).filter(Boolean),
                dislikes: form.dislikes.split(",").map((s) => s.trim()).filter(Boolean),
                favourite_cocktails: form.favourite_cocktails.split(",").map((s) => s.trim()).filter(Boolean),
                notes: form.notes,
            });
            setForm({ name: "", likes: "", dislikes: "", favourite_cocktails: "", notes: "" });
            setShowForm(false);
            toast.success(`${form.name} added`);
            load();
        } catch {
            toast.error("Save failed");
        }
    };

    const remove = async (id) => {
        if (!window.confirm("Remove this regular?")) return;
        try {
            await api.delete(`/regulars/${id}`);
            load();
        } catch {
            toast.error("Failed");
        }
    };

    return (
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
            <Toaster position="top-center" theme="dark" />
            <PageHeader
                eyebrow="Customer book"
                title="The Regulars"
                subtitle="Sheldon uses these notes when you ask 'what should Sarah drink tonight?'"
            >
                <button onClick={() => setShowForm(!showForm)} className="btn-amber flex items-center gap-2" data-testid="add-regular-btn">
                    <Plus size={16} weight="bold" /> {showForm ? "Close" : "Add Regular"}
                </button>
            </PageHeader>

            {showForm && (
                <div className="tool-card mb-6 fade-in">
                    <div className="grid sm:grid-cols-2 gap-4">
                        <div className="sm:col-span-2">
                            <div className="label-tiny mb-1">Name</div>
                            <input className="input-dark" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="regular-name" />
                        </div>
                        <div>
                            <div className="label-tiny mb-1">Likes (comma separated)</div>
                            <input className="input-dark" placeholder="mezcal, smoky, bitter" value={form.likes} onChange={(e) => setForm({ ...form, likes: e.target.value })} />
                        </div>
                        <div>
                            <div className="label-tiny mb-1">Dislikes</div>
                            <input className="input-dark" placeholder="cilantro, anise" value={form.dislikes} onChange={(e) => setForm({ ...form, dislikes: e.target.value })} />
                        </div>
                        <div className="sm:col-span-2">
                            <div className="label-tiny mb-1">Favourite cocktails</div>
                            <input className="input-dark" placeholder="Negroni, Espresso Martini" value={form.favourite_cocktails} onChange={(e) => setForm({ ...form, favourite_cocktails: e.target.value })} />
                        </div>
                        <div className="sm:col-span-2">
                            <div className="label-tiny mb-1">Notes</div>
                            <textarea className="input-dark" rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
                        </div>
                    </div>
                    <button onClick={save} className="btn-amber mt-4" data-testid="regular-save">Save</button>
                </div>
            )}

            {regulars.length === 0 ? (
                <div className="text-center py-16" style={{ color: "var(--text-secondary)" }}>
                    No regulars yet. Add one to build Sheldon's memory of your bar.
                </div>
            ) : (
                <div className="grid sm:grid-cols-2 gap-4">
                    {regulars.map((r) => (
                        <div key={r.id} className="tool-card" data-testid={`regular-card-${r.name.toLowerCase()}`}>
                            <div className="flex items-start justify-between gap-3 mb-3">
                                <div className="flex items-center gap-3">
                                    <div className="brand-mark" style={{ width: 36, height: 36 }} />
                                    <h3 className="font-serif text-2xl" style={{ color: "var(--text-primary)" }}>{r.name}</h3>
                                </div>
                                <button onClick={() => remove(r.id)} className="p-2 rounded hover:bg-white/5" data-testid={`delete-regular-${r.id}`}>
                                    <Trash size={16} style={{ color: "var(--text-secondary)" }} />
                                </button>
                            </div>
                            {r.favourite_cocktails?.length > 0 && (
                                <div className="mb-2">
                                    <div className="label-tiny mb-1">Faves</div>
                                    <div className="flex flex-wrap gap-1">
                                        {r.favourite_cocktails.map((f) => <span key={f} className="badge badge-amber">{f}</span>)}
                                    </div>
                                </div>
                            )}
                            {r.likes?.length > 0 && (
                                <div className="text-sm mb-1"><span className="label-tiny mr-2">Likes:</span> {r.likes.join(", ")}</div>
                            )}
                            {r.dislikes?.length > 0 && (
                                <div className="text-sm mb-1"><span className="label-tiny mr-2">Dislikes:</span> {r.dislikes.join(", ")}</div>
                            )}
                            {r.notes && <p className="text-sm mt-2" style={{ color: "var(--text-secondary)" }}>{r.notes}</p>}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
