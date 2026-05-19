import { useState } from "react";
import type { Face } from "../types";
import { GitMerge, Trash2, Users, X } from "lucide-react";

interface Props {
  faces: Face[];
  onSelect: (face: Face) => void;
  onMerge: (targetFaceId: string, sourceFaceIds: string[]) => Promise<void>;
  onDelete: (faceIds: string[]) => Promise<void>;
  merging: boolean;
  deleting: boolean;
}

type Mode = "idle" | "merge" | "delete";

export function FaceGrid({ faces, onSelect, onMerge, onDelete, merging, deleting }: Props) {
  const [filter, setFilter] = useState("");
  const [mode, setMode] = useState<Mode>("idle");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const visible = filter.trim()
    ? faces.filter((f) =>
        (f.label ?? "").toLowerCase().includes(filter.toLowerCase())
      )
    : faces;
  const selectedFaces = faces.filter((face) => selectedIds.has(face.id));

  function toggleSelected(face: Face) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(face.id)) {
        next.delete(face.id);
      } else {
        next.add(face.id);
      }
      return next;
    });
  }

  function resetMode() {
    setSelectedIds(new Set());
    setMode("idle");
  }

  async function handleMerge() {
    if (selectedFaces.length < 2) return;
    const [target, ...sources] = selectedFaces;
    await onMerge(target.id, sources.map((face) => face.id));
    resetMode();
  }

  async function handleDelete() {
    if (selectedFaces.length === 0) return;
    const ok = window.confirm(
      `${selectedFaces.length} kişi klasörü silinsin mi? Fotoğraflar silinmez.`
    );
    if (!ok) return;
    await onDelete(selectedFaces.map((face) => face.id));
    resetMode();
  }

  return (
    <section className="w-full">
      {/* search bar */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <Users className="text-brand-500 shrink-0" size={20} />
        <input
          type="search"
          placeholder="İsim ara..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-full max-w-sm rounded-xl border border-gray-200 bg-white px-4 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
        />
        {mode === "merge" ? (
          <>
            <button
              type="button"
              onClick={handleMerge}
              disabled={selectedFaces.length < 2 || merging}
              className="inline-flex items-center gap-2 rounded-lg bg-brand-500 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <GitMerge size={16} />
              {merging ? "Birleştiriliyor" : "Birleştir"}
            </button>
            <button
              type="button"
              onClick={resetMode}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-semibold text-gray-600 shadow-sm transition hover:bg-gray-50"
            >
              <X size={16} />
              İptal
            </button>
            <span className="text-sm text-gray-400">{selectedFaces.length} seçili</span>
          </>
        ) : mode === "delete" ? (
          <>
            <button
              type="button"
              onClick={handleDelete}
              disabled={selectedFaces.length === 0 || deleting}
              className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Trash2 size={16} />
              {deleting ? "Siliniyor" : "Sil"}
            </button>
            <button
              type="button"
              onClick={resetMode}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-semibold text-gray-600 shadow-sm transition hover:bg-gray-50"
            >
              <X size={16} />
              İptal
            </button>
            <span className="text-sm text-gray-400">{selectedFaces.length} seçili</span>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => setMode("merge")}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-semibold text-gray-600 shadow-sm transition hover:bg-gray-50"
            >
              <GitMerge size={16} />
              Birleştir
            </button>
            <button
              type="button"
              onClick={() => setMode("delete")}
              className="inline-flex items-center gap-2 rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-semibold text-red-600 shadow-sm transition hover:bg-red-50"
            >
              <Trash2 size={16} />
              Sil
            </button>
          </>
        )}
        <span className="ml-auto shrink-0 text-sm text-gray-400">
          {visible.length} kişi
        </span>
      </div>

      {/* face grid */}
      <div className="grid grid-cols-3 gap-4 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-7 xl:grid-cols-8">
        {visible.map((face) => (
          <FaceCard
            key={face.id}
            face={face}
            selected={selectedIds.has(face.id)}
            mode={mode}
            href={`/faces/${encodeURIComponent(face.id)}`}
            onClick={() => mode === "idle" ? onSelect(face) : toggleSelected(face)}
          />
        ))}
      </div>

      {visible.length === 0 && (
        <p className="mt-16 text-center text-sm text-gray-400">
          Sonuç bulunamadı
        </p>
      )}
    </section>
  );
}

function FaceCard({
  face,
  selected,
  mode,
  href,
  onClick,
}: {
  face: Face;
  selected: boolean;
  mode: Mode;
  href: string;
  onClick: () => void;
}) {
  const selectedClass = mode === "delete"
    ? "bg-red-50 ring-2 ring-red-500"
    : "bg-brand-50 ring-2 ring-brand-500";
  const hoverClass = mode === "delete"
    ? "hover:bg-red-50 focus-visible:ring-red-500"
    : "hover:bg-brand-50 focus-visible:ring-brand-500";
  const imageHoverClass = mode === "delete"
    ? "group-hover:ring-red-500"
    : "group-hover:ring-brand-500";
  const cardClass = `group flex flex-col items-center gap-3 rounded-2xl p-2 transition-all focus-visible:outline-none focus-visible:ring-2 ${hoverClass} ${
    selected ? selectedClass : ""
  }`;
  const countLabel = face.photo_count > 99 ? "99+" : String(face.photo_count ?? 0);

  const content = (
    <>
      <div className="relative h-16 w-16 sm:h-20 sm:w-20">
        <div className={`h-full w-full overflow-hidden rounded-full ring-2 ring-transparent transition-all ${imageHoverClass}`}>
          <img
            src={face.avatar_url}
            alt={face.label ?? "Yüz"}
            className="h-full w-full object-cover transition-transform group-hover:scale-110"
            loading="lazy"
            decoding="async"
          />
        </div>
        <span className="absolute -bottom-1 -right-1 z-10 flex h-6 min-w-6 items-center justify-center rounded-full bg-brand-500 px-1 text-[10px] font-bold leading-none text-white shadow-sm ring-2 ring-white">
          {countLabel}
        </span>
        {mode !== "idle" && selected && (
          <span className={`absolute -left-1 -top-1 z-10 flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold text-white shadow-sm ring-2 ring-white ${mode === "delete" ? "bg-red-600" : "bg-emerald-500"}`}>
            {mode === "delete" ? <Trash2 size={12} /> : "✓"}
          </span>
        )}
      </div>
      <span className="max-w-full truncate text-xs text-gray-600 group-hover:text-brand-600">
        {face.label ?? "Kişi"}
      </span>
    </>
  );

  if (mode === "idle") {
    return (
      <a
        href={href}
        onClick={(event) => {
          if (
            event.defaultPrevented ||
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
          ) {
            return;
          }
          event.preventDefault();
          onClick();
        }}
        className={cardClass}
      >
        {content}
      </a>
    );
  }

  return (
    <button type="button" onClick={onClick} className={cardClass}>
      {content}
    </button>
  );
}
