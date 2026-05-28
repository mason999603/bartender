import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Toaster, toast } from "sonner";
import { Plus, Trash, X, Stack, VinylRecord, BookOpen, FilmStrip, MusicNotes, Star } from "@phosphor-icons/react";

const ICONS = {
    stack: Stack,
    vinyl: VinylRecord,
    book: BookOpen,
    film: FilmStrip,
    music: MusicNotes,
};

const PRESETS = [
    { name: "Records", icon: "vinyl", description: "My vinyl collection — artist, album, year, condition." },
    { name: "Books", icon: "book", description: "Books read or to read." },
    { name: "Movies", icon: "film", description: "Watched, want to watch, favourites." },
    { name: "Playlists", icon: "music", description: "Set lists, vibes, bar music." },
];

export default function CollectionsPage() {
    const [collections, setCollections] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showCreate, setShowCreate] = useState(false);
    const [openId, setOpenId] = useState(null);

    const load = async () => {
        setLoading(true);
        try {
            const r = await api.get("/collections");
            setCollections(r.data || []);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { load(); }, []);

    const createCollection = async (preset) => {
        try {
            await api.post("/collections", preset);
            toast.success(`Created "${preset.name}"`);
            setShowCreate(false);
            load();
        } catch (e) {
            toast.error("Couldn't create");
        }
    };

    const deleteCollection = async (id) => {
        if (!window.confirm("Delete this whole collection?")) return;
        await api.delete(`/collections/${id}`);
        if (openId === id) setOpenId(null);
        load();
    };

    const openCollection = collections.find((c) => c.id === openId);

    return (
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
            <Toaster position="top-center" theme="dark" />
            <PageHeader
                eyebrow="What Russell remembers"
                title="Collections"
                subtitle="Russell can keep track of anything you want him to — your records, books, movies, set lists. He references them naturally in conversation."
            >
                <button onClick={() => setShowCreate(true)} className="btn-amber flex items-center gap-2" data-testid="new-collection-btn">
                    <Plus size={16} weight="bold" /> New Collection
                </button>
            </PageHeader>

            {loading ? (
                <div className="text-center py-16" style={{ color: "var(--text-secondary)" }}>Pulling crates…</div>
            ) : collections.length === 0 ? (
                <div className="tool-card text-center py-12">
                    <Stack size={48} className="mx-auto mb-4" style={{ color: "var(--text-muted)" }} />
                    <div className="font-serif text-2xl mb-2" style={{ color: "var(--text-primary)" }}>
                        Nothing in the crates yet
                    </div>
                    <p className="text-sm mb-6" style={{ color: "var(--text-secondary)" }}>
                        Start with one of these, or roll your own.
                    </p>
                    <div className="grid sm:grid-cols-2 gap-3 max-w-xl mx-auto">
                        {PRESETS.map((p) => {
                            const Icon = ICONS[p.icon] || Stack;
                            return (
                                <button
                                    key={p.name}
                                    onClick={() => createCollection(p)}
                                    className="tool-card flex items-center gap-3 text-left"
                                    data-testid={`preset-${p.name.toLowerCase()}`}
                                >
                                    <Icon size={24} weight="bold" style={{ color: "var(--accent)" }} />
                                    <div>
                                        <div className="font-serif text-lg" style={{ color: "var(--text-primary)" }}>{p.name}</div>
                                        <div className="text-xs" style={{ color: "var(--text-secondary)" }}>{p.description}</div>
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                </div>
            ) : (
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
                    {collections.map((c) => {
                        const Icon = ICONS[c.icon] || Stack;
                        return (
                            <button
                                key={c.id}
                                onClick={() => setOpenId(c.id)}
                                className="tool-card text-left"
                                data-testid={`collection-card-${c.name.toLowerCase().replace(/\s+/g, "-")}`}
                            >
                                <div className="flex items-start justify-between gap-3 mb-3">
                                    <Icon size={32} weight="bold" style={{ color: "var(--accent)" }} />
                                    <span className="badge">{(c.items || []).length} items</span>
                                </div>
                                <h3 className="font-serif text-2xl mb-1" style={{ color: "var(--text-primary)" }}>{c.name}</h3>
                                {c.description && (
                                    <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{c.description}</p>
                                )}
                            </button>
                        );
                    })}
                </div>
            )}

            {showCreate && (
                <CreateCollectionModal
                    onClose={() => setShowCreate(false)}
                    onCreated={(p) => createCollection(p)}
                />
            )}

            {openCollection && (
                <CollectionDetailModal
                    collection={openCollection}
                    onClose={() => { setOpenId(null); load(); }}
                    onDelete={() => deleteCollection(openCollection.id)}
                    onReload={load}
                />
            )}
        </div>
    );
}


function CreateCollectionModal({ onClose, onCreated }) {
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [icon, setIcon] = useState("stack");

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 fade-in"
            style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)" }}
            onClick={onClose}
        >
            <div
                className="glass-strong rounded-2xl max-w-lg w-full p-8"
                onClick={(e) => e.stopPropagation()}
                data-testid="create-collection-modal"
            >
                <div className="flex items-center justify-between mb-6">
                    <h2 className="font-serif text-3xl" style={{ color: "var(--accent)" }}>New Collection</h2>
                    <button onClick={onClose} className="p-2 rounded hover:bg-white/5"><X size={18} /></button>
                </div>

                <div className="space-y-4">
                    <div>
                        <div className="label-tiny mb-1">Name</div>
                        <input className="input-dark" placeholder="Records" value={name} onChange={(e) => setName(e.target.value)} data-testid="new-col-name" />
                    </div>
                    <div>
                        <div className="label-tiny mb-1">Description (optional)</div>
                        <input className="input-dark" placeholder="What Russell should know about this" value={description} onChange={(e) => setDescription(e.target.value)} />
                    </div>
                    <div>
                        <div className="label-tiny mb-2">Icon</div>
                        <div className="flex gap-2 flex-wrap">
                            {Object.entries(ICONS).map(([key, Icon]) => (
                                <button
                                    key={key}
                                    onClick={() => setIcon(key)}
                                    className="p-3 rounded-lg border"
                                    style={{
                                        borderColor: icon === key ? "var(--accent)" : "rgba(255,255,255,0.1)",
                                        background: icon === key ? "rgba(224,145,50,0.1)" : "rgba(255,255,255,0.03)",
                                    }}
                                >
                                    <Icon size={20} weight="bold" style={{ color: icon === key ? "var(--accent)" : "var(--text-secondary)" }} />
                                </button>
                            ))}
                        </div>
                    </div>
                    <button
                        onClick={() => {
                            if (!name.trim()) return toast.error("Name required");
                            onCreated({ name, description, icon });
                        }}
                        className="btn-amber w-full"
                        data-testid="new-col-save"
                    >
                        Create
                    </button>
                </div>
            </div>
        </div>
    );
}


function CollectionDetailModal({ collection, onClose, onDelete, onReload }) {
    const [title, setTitle] = useState("");
    const [subtitle, setSubtitle] = useState("");
    const [tagsInput, setTagsInput] = useState("");
    const [notes, setNotes] = useState("");
    const [rating, setRating] = useState(0);
    const [items, setItems] = useState(collection.items || []);
    const [adding, setAdding] = useState(false);

    const Icon = ICONS[collection.icon] || Stack;

    const addItem = async () => {
        if (!title.trim()) return toast.error("Title required");
        setAdding(true);
        try {
            const res = await api.post(`/collections/${collection.id}/items`, {
                title: title.trim(),
                subtitle: subtitle.trim(),
                tags: tagsInput.split(",").map((s) => s.trim()).filter(Boolean),
                notes: notes.trim(),
                rating: rating || null,
            });
            setItems([res.data, ...items]);
            setTitle("");
            setSubtitle("");
            setTagsInput("");
            setNotes("");
            setRating(0);
            onReload();
        } catch (e) {
            toast.error("Couldn't add");
        } finally {
            setAdding(false);
        }
    };

    const removeItem = async (itemId) => {
        try {
            await api.delete(`/collections/${collection.id}/items/${itemId}`);
            setItems(items.filter((i) => i.id !== itemId));
            onReload();
        } catch {
            toast.error("Failed");
        }
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 fade-in"
            style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)" }}
            onClick={onClose}
        >
            <div
                className="glass-strong rounded-2xl max-w-3xl w-full max-h-[88vh] overflow-y-auto p-8"
                onClick={(e) => e.stopPropagation()}
                data-testid="collection-detail-modal"
            >
                <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-3">
                        <Icon size={32} weight="bold" style={{ color: "var(--accent)" }} />
                        <div>
                            <h2 className="font-serif text-3xl" style={{ color: "var(--text-primary)" }}>{collection.name}</h2>
                            {collection.description && (
                                <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{collection.description}</p>
                            )}
                        </div>
                    </div>
                    <div className="flex gap-2">
                        <button onClick={onDelete} className="btn-ghost text-xs flex items-center gap-1" data-testid="delete-collection">
                            <Trash size={14} /> Delete
                        </button>
                        <button onClick={onClose} className="p-2 rounded hover:bg-white/5"><X size={18} /></button>
                    </div>
                </div>

                {/* Add item */}
                <div className="tool-card mb-6">
                    <div className="label-tiny mb-3">Add new item</div>
                    <div className="grid sm:grid-cols-2 gap-3 mb-3">
                        <input className="input-dark" placeholder="Title (e.g. Dark Side of the Moon)" value={title} onChange={(e) => setTitle(e.target.value)} data-testid="item-title" />
                        <input className="input-dark" placeholder="Subtitle (artist · year)" value={subtitle} onChange={(e) => setSubtitle(e.target.value)} data-testid="item-subtitle" />
                    </div>
                    <input className="input-dark mb-3" placeholder="Tags (comma separated — e.g. prog, classic, 1973)" value={tagsInput} onChange={(e) => setTagsInput(e.target.value)} data-testid="item-tags" />
                    <textarea className="input-dark mb-3" rows={2} placeholder="Notes (optional — condition, memories, why you love it)" value={notes} onChange={(e) => setNotes(e.target.value)} data-testid="item-notes" />
                    <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-1" data-testid="item-rating">
                            <span className="label-tiny mr-2">Rating</span>
                            {[1, 2, 3, 4, 5].map((n) => (
                                <button key={n} onClick={() => setRating(rating === n ? 0 : n)} className="p-1">
                                    <Star size={18} weight={n <= rating ? "fill" : "regular"} style={{ color: n <= rating ? "var(--accent)" : "var(--text-muted)" }} />
                                </button>
                            ))}
                        </div>
                        <button onClick={addItem} disabled={adding} className="btn-amber" data-testid="add-item-btn">
                            <Plus size={14} weight="bold" className="inline mr-1" /> Add
                        </button>
                    </div>
                </div>

                {/* Items */}
                {items.length === 0 ? (
                    <div className="text-center py-12" style={{ color: "var(--text-secondary)" }}>
                        Nothing yet. Add your first item above.
                    </div>
                ) : (
                    <div className="space-y-2">
                        {items.map((i) => (
                            <div key={i.id} className="tool-card flex items-start justify-between gap-3" style={{ padding: "14px 18px" }} data-testid={`collection-item-${i.id}`}>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-baseline gap-2 mb-1">
                                        <span className="font-serif text-lg" style={{ color: "var(--text-primary)" }}>{i.title}</span>
                                        {i.subtitle && <span className="text-sm" style={{ color: "var(--text-secondary)" }}>· {i.subtitle}</span>}
                                    </div>
                                    {i.tags && i.tags.length > 0 && (
                                        <div className="flex gap-1 flex-wrap mb-1">
                                            {i.tags.map((t) => <span key={t} className="badge">{t}</span>)}
                                        </div>
                                    )}
                                    {i.notes && <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{i.notes}</p>}
                                    {i.rating > 0 && (
                                        <div className="flex items-center gap-0.5 mt-1">
                                            {Array.from({ length: i.rating }).map((_, idx) => (
                                                <Star key={idx} size={12} weight="fill" style={{ color: "var(--accent)" }} />
                                            ))}
                                        </div>
                                    )}
                                </div>
                                <button onClick={() => removeItem(i.id)} className="p-2 rounded hover:bg-white/5">
                                    <Trash size={14} style={{ color: "var(--text-secondary)" }} />
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
