import React, { useState, useEffect } from "react";
import { api } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Toaster, toast } from "sonner";
import { Plus, Trash, Brain } from "@phosphor-icons/react";

export default function MemoryPage() {
    const [memories, setMemories] = useState([]);
    const [key, setKey] = useState("");
    const [value, setValue] = useState("");

    const load = async () => {
        const res = await api.get("/memory");
        setMemories(res.data || []);
    };

    useEffect(() => {
        load();
    }, []);

    const save = async () => {
        if (!key.trim() || !value.trim()) return toast.error("Both fields required");
        try {
            await api.post("/memory", { key, value });
            setKey("");
            setValue("");
            toast.success("Saved");
            load();
        } catch {
            toast.error("Save failed");
        }
    };

    const remove = async (id) => {
        try {
            await api.delete(`/memory/${id}`);
            load();
        } catch {
            toast.error("Failed");
        }
    };

    return (
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
            <Toaster position="top-center" theme="dark" />
            <PageHeader
                eyebrow="The Brain"
                title="What Russell Remembers"
                subtitle="Permanent notes Russell uses in every conversation. Your bar's vibe, your style, your dietary stuff — whatever you want him to know forever."
            />

            <div className="tool-card mb-6">
                <div className="grid sm:grid-cols-5 gap-2">
                    <input
                        className="input-dark sm:col-span-2"
                        placeholder="Key (e.g. 'house style')"
                        value={key}
                        onChange={(e) => setKey(e.target.value)}
                        data-testid="memory-key"
                    />
                    <input
                        className="input-dark sm:col-span-2"
                        placeholder="Value (e.g. 'we lean dry, low-sugar')"
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && save()}
                        data-testid="memory-value"
                    />
                    <button onClick={save} className="btn-amber" data-testid="memory-save">
                        <Plus size={16} weight="bold" className="inline mr-1" /> Save
                    </button>
                </div>
            </div>

            {memories.length === 0 ? (
                <div className="text-center py-16" style={{ color: "var(--text-secondary)" }}>
                    <Brain size={48} className="mx-auto mb-4 opacity-40" />
                    No memories yet. Tell Russell what to remember.
                </div>
            ) : (
                <div className="space-y-3">
                    {memories.map((m) => (
                        <div key={m.id} className="tool-card flex items-start justify-between gap-4" data-testid={`memory-${m.id}`}>
                            <div className="flex-1">
                                <div className="label-tiny mb-1">{m.key}</div>
                                <div className="text-base" style={{ color: "var(--text-primary)" }}>{m.value}</div>
                            </div>
                            <button onClick={() => remove(m.id)} className="p-2 rounded hover:bg-white/5">
                                <Trash size={16} style={{ color: "var(--text-secondary)" }} />
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
