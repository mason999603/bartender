import React, { useState, useEffect } from "react";
import { api } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Toaster, toast } from "sonner";
import { Plus, Trash } from "@phosphor-icons/react";

export default function InventoryPage() {
    const [items, setItems] = useState([]);
    const [name, setName] = useState("");

    const load = async () => {
        const res = await api.get("/inventory");
        setItems(res.data || []);
    };

    useEffect(() => {
        load();
    }, []);

    const add = async () => {
        if (!name.trim()) return;
        try {
            await api.post("/inventory", { name: name.trim(), in_stock: true });
            setName("");
            load();
        } catch {
            toast.error("Failed");
        }
    };

    const toggle = async (id, in_stock) => {
        try {
            await api.patch(`/inventory/${id}`, null, { params: { in_stock: !in_stock } });
            load();
        } catch {
            toast.error("Failed");
        }
    };

    const remove = async (id) => {
        try {
            await api.delete(`/inventory/${id}`);
            load();
        } catch {
            toast.error("Failed");
        }
    };

    const inStock = items.filter((i) => i.in_stock);
    const out = items.filter((i) => !i.in_stock);

    return (
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
            <Toaster position="top-center" theme="dark" />
            <PageHeader
                eyebrow="Bar inventory"
                title="What's on the back bar"
                subtitle="Tracked items help Russell answer 'what can I make right now?' accurately. Off-tracker = assumed available."
            />

            <div className="tool-card mb-6">
                <div className="flex gap-2">
                    <input
                        className="input-dark flex-1"
                        placeholder="e.g. Mezcal Vida"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && add()}
                        data-testid="inv-name"
                    />
                    <button onClick={add} className="btn-amber" data-testid="inv-add">
                        <Plus size={16} weight="bold" />
                    </button>
                </div>
            </div>

            {items.length === 0 ? (
                <div className="text-center py-16" style={{ color: "var(--text-secondary)" }}>
                    Empty. Add bottles as you go.
                </div>
            ) : (
                <div className="grid sm:grid-cols-2 gap-6">
                    <div>
                        <div className="label-tiny mb-3">In stock · {inStock.length}</div>
                        <div className="space-y-2">
                            {inStock.map((i) => (
                                <div key={i.id} className="tool-card flex items-center justify-between" style={{ padding: "12px 16px" }}>
                                    <button onClick={() => toggle(i.id, i.in_stock)} className="flex items-center gap-3 flex-1 text-left" data-testid={`inv-toggle-${i.id}`}>
                                        <span
                                            className="rounded-full border-2"
                                            style={{ width: 18, height: 18, background: "var(--accent)", borderColor: "var(--accent)" }}
                                        />
                                        <span>{i.name}</span>
                                    </button>
                                    <button onClick={() => remove(i.id)} className="p-1 rounded hover:bg-white/5">
                                        <Trash size={14} style={{ color: "var(--text-secondary)" }} />
                                    </button>
                                </div>
                            ))}
                        </div>
                    </div>
                    <div>
                        <div className="label-tiny mb-3">86'd · {out.length}</div>
                        <div className="space-y-2">
                            {out.map((i) => (
                                <div key={i.id} className="tool-card flex items-center justify-between" style={{ padding: "12px 16px", opacity: 0.6 }}>
                                    <button onClick={() => toggle(i.id, i.in_stock)} className="flex items-center gap-3 flex-1 text-left">
                                        <span
                                            className="rounded-full border-2"
                                            style={{ width: 18, height: 18, borderColor: "var(--text-muted)" }}
                                        />
                                        <span style={{ textDecoration: "line-through" }}>{i.name}</span>
                                    </button>
                                    <button onClick={() => remove(i.id)} className="p-1 rounded hover:bg-white/5">
                                        <Trash size={14} style={{ color: "var(--text-secondary)" }} />
                                    </button>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
