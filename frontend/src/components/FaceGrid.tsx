import { useState } from "react";
import type { Face } from "../types";
import { CheckCircle2, Circle, GitMerge, Trash2, Users, XCircle } from "lucide-react";

interface Props {
  faces: Face[];
  isAdmin: boolean;
  selectedFaceIds: Set<string>;
  actionLoading: boolean;
  onSelect: (face: Face) => void;
  onToggleFace: (faceId: string) => void;
  onMergeSelected: () => void;
  onDeleteSelected: () => void;
}

export function FaceGrid({
  faces,
  isAdmin,
  selectedFaceIds,
  actionLoading,
  onSelect,
  onToggleFace,
  onMergeSelected,
  onDeleteSelected,
}: Props) {
  const [filter, setFilter] = useState("");
  const selectedCount = selectedFaceIds.size;

  const visible = filter.trim()
    ? faces.filter((f) =>
        (f.label ?? "").toLowerCase().includes(filter.toLowerCase())
      )
    : faces;

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
        <span className="ml-auto shrink-0 text-sm text-gray-400">
          {visible.length} kişi
        </span>
      </div>

      {isAdmin && (
        <div className="mb-5 flex flex-wrap items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 py-3 shadow-sm">
          <span className="mr-auto text-sm font-medium text-gray-600">
            {selectedCount > 0 ? `${selectedCount} kişi seçili` : "Admin araçları"}
          </span>
          {selectedCount > 0 && (
            <button
              type="button"
              onClick={() => selectedFaceIds.forEach(onToggleFace)}
              disabled={actionLoading}
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <XCircle size={16} />
              Temizle
            </button>
          )}
          <button
            type="button"
            onClick={onMergeSelected}
            disabled={actionLoading || selectedCount < 2}
            className="inline-flex items-center gap-1.5 rounded-lg bg-brand-500 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <GitMerge size={16} />
            Birleştir
          </button>
          <button
            type="button"
            onClick={onDeleteSelected}
            disabled={actionLoading || selectedCount < 1}
            className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Trash2 size={16} />
            Sil
          </button>
        </div>
      )}

      {/* face grid */}
      <div className="grid grid-cols-3 gap-4 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-7 xl:grid-cols-8">
        {visible.map((face) => (
          <FaceCard
            key={face.id}
            face={face}
            href={`/faces/${encodeURIComponent(face.id)}`}
            isAdmin={isAdmin}
            isSelected={selectedFaceIds.has(face.id)}
            onClick={() => onSelect(face)}
            onToggle={() => onToggleFace(face.id)}
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
  href,
  isAdmin,
  isSelected,
  onClick,
  onToggle,
}: {
  face: Face;
  href: string;
  isAdmin: boolean;
  isSelected: boolean;
  onClick: () => void;
  onToggle: () => void;
}) {
  const cardClass = "group flex flex-col items-center gap-3 rounded-2xl p-2 transition-all hover:bg-brand-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500";
  const countLabel = face.photo_count > 99 ? "99+" : String(face.photo_count ?? 0);

  return (
    <div className="relative">
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
        className={`${cardClass} ${isSelected ? "bg-brand-50 ring-2 ring-brand-500" : ""}`}
      >
        <div className="relative h-16 w-16 sm:h-20 sm:w-20">
          <div className="h-full w-full overflow-hidden rounded-full ring-2 ring-transparent transition-all group-hover:ring-brand-500">
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
        </div>
        <span className="max-w-full truncate text-xs text-gray-600 group-hover:text-brand-600">
          {face.label ?? "Kişi"}
        </span>
      </a>
      {isAdmin && (
        <button
          type="button"
          onClick={onToggle}
          aria-pressed={isSelected}
          title={isSelected ? "Seçimi kaldır" : "Seç"}
          className={`absolute right-0 top-0 z-10 rounded-full bg-white p-1 shadow-sm ring-1 transition-colors ${
            isSelected
              ? "text-brand-600 ring-brand-500"
              : "text-gray-400 ring-gray-200 hover:text-brand-600"
          }`}
        >
          {isSelected ? <CheckCircle2 size={20} /> : <Circle size={20} />}
        </button>
      )}
    </div>
  );
}
