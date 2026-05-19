import { useState } from "react";
import type { Face, Photo } from "../types";
import { ArrowLeft, Download, X, ChevronLeft, ChevronRight } from "lucide-react";

interface Props {
  face: Face;
  photos: Photo[];
  onBack: () => void;
}

export function PhotoGallery({ face, photos, onBack }: Props) {
  const [lightbox, setLightbox] = useState<number | null>(null);

  function openLightbox(idx: number) { setLightbox(idx); }
  function closeLightbox() { setLightbox(null); }
  function prev() { setLightbox((i) => (i! - 1 + photos.length) % photos.length); }
  function next() { setLightbox((i) => (i! + 1) % photos.length); }

  return (
    <section className="w-full animate-fade-in">
      {/* header */}
      <div className="mb-6 flex items-center gap-4">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-600 shadow-sm hover:border-brand-500 hover:text-brand-600 transition-colors"
        >
          <ArrowLeft size={16} />
          Geri
        </button>

        <img
          src={face.avatar_url}
          alt={face.label ?? "Yüz"}
          className="h-11 w-11 rounded-full object-cover ring-2 ring-brand-500"
        />

        <div>
          <h2 className="font-semibold text-gray-900">{face.label ?? "Kişi"}</h2>
          <p className="text-xs text-gray-500">{photos.length} fotoğraf</p>
        </div>
      </div>

      {/* masonry grid */}
      <div className="columns-2 gap-3 sm:columns-3 md:columns-4 lg:columns-5">
        {photos.map((photo, idx) => (
          <div
            key={photo.id}
            className="mb-3 break-inside-avoid cursor-zoom-in overflow-hidden rounded-xl shadow-sm transition-transform hover:scale-[1.02]"
            onClick={() => openLightbox(idx)}
          >
            <img
              src={photo.url}
              alt=""
              className="w-full object-cover"
              loading="lazy"
              decoding="async"
            />
          </div>
        ))}
      </div>

      {photos.length === 0 && (
        <p className="mt-24 text-center text-sm text-gray-400">
          Bu kişi için fotoğraf bulunamadı.
        </p>
      )}

      {/* lightbox */}
      {lightbox !== null && (
        <Lightbox
          photo={photos[lightbox]}
          index={lightbox}
          total={photos.length}
          onClose={closeLightbox}
          onPrev={prev}
          onNext={next}
        />
      )}
    </section>
  );
}

interface LightboxProps {
  photo: Photo;
  index: number;
  total: number;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
}

function Lightbox({ photo, index, total, onClose, onPrev, onNext }: LightboxProps) {
  async function handleDownload() {
    try {
      const res = await fetch(photo.url);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dentco-outliers_${photo.id}.jpg`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      window.open(photo.url, "_blank");
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 animate-fade-in"
      onClick={onClose}
    >
      {/* counter */}
      <span className="absolute left-1/2 top-4 -translate-x-1/2 rounded-full bg-white/10 px-3 py-1 text-xs text-white/80">
        {index + 1} / {total}
      </span>

      {/* controls */}
      <button onClick={(e) => { e.stopPropagation(); onClose(); }}
        className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20 transition-colors">
        <X size={20} />
      </button>
      <button onClick={(e) => { e.stopPropagation(); handleDownload(); }}
        className="absolute right-16 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20 transition-colors">
        <Download size={20} />
      </button>

      <button onClick={(e) => { e.stopPropagation(); onPrev(); }}
        className="absolute left-4 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-3 text-white hover:bg-white/20 transition-colors">
        <ChevronLeft size={24} />
      </button>
      <button onClick={(e) => { e.stopPropagation(); onNext(); }}
        className="absolute right-4 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-3 text-white hover:bg-white/20 transition-colors">
        <ChevronRight size={24} />
      </button>

      {/* image */}
      <img
        src={photo.url}
        alt=""
        className="max-h-[90vh] max-w-[90vw] rounded-xl object-contain shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}
