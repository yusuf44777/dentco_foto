import { useEffect, useState } from "react";
import { FaceGrid } from "./components/FaceGrid";
import { PhotoGallery } from "./components/PhotoGallery";
import { useFaces, useFacePhotos } from "./hooks/useEvent";
import { api } from "./lib/api";
import type { Face } from "./types";

const FACE_ROUTE_PREFIX = "/faces/";

function facePath(faceId: string) {
  return `${FACE_ROUTE_PREFIX}${encodeURIComponent(faceId)}`;
}

function getFaceIdFromPath() {
  const { pathname } = window.location;
  if (!pathname.startsWith(FACE_ROUTE_PREFIX)) return null;
  const raw = pathname.slice(FACE_ROUTE_PREFIX.length).split("/")[0];
  return raw ? decodeURIComponent(raw) : null;
}

export default function App() {
  const { faces, loading: facesLoading, error, reload } = useFaces();
  const [selectedFaceId, setSelectedFaceId] = useState<string | null>(() => getFaceIdFromPath());
  const [actionError, setActionError] = useState<string | null>(null);
  const [merging, setMerging] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const selectedFace = selectedFaceId
    ? faces.find((face) => face.id === selectedFaceId) ?? null
    : null;
  const { photos, loading: photosLoading } = useFacePhotos(selectedFace?.id ?? null);

  useEffect(() => {
    function handlePopState() {
      setSelectedFaceId(getFaceIdFromPath());
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (!selectedFaceId || facesLoading || faces.length === 0 || selectedFace) return;
    setActionError("Bu kişi klasörü bulunamadı ya da silinmiş.");
    navigateHome({ replace: true });
  }, [faces, facesLoading, selectedFace, selectedFaceId]);

  function navigateHome({ replace = false } = {}) {
    const method = replace ? "replaceState" : "pushState";
    window.history[method]({ view: "home" }, "", "/");
    setSelectedFaceId(null);
  }

  function handleSelectFace(face: Face) {
    window.history.pushState({ view: "face", faceId: face.id }, "", facePath(face.id));
    setSelectedFaceId(face.id);
  }

  async function handleMerge(targetFaceId: string, sourceFaceIds: string[]) {
    setMerging(true);
    setActionError(null);
    try {
      await api.faces.merge(targetFaceId, sourceFaceIds);
      navigateHome({ replace: true });
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? `Birleştirme hatası: ${e.message}` : "Birleştirme başarısız oldu");
    } finally {
      setMerging(false);
    }
  }

  async function handleDelete(faceIds: string[]) {
    setDeleting(true);
    setActionError(null);
    try {
      await api.faces.deleteMany(faceIds);
      if (selectedFaceId && faceIds.includes(selectedFaceId)) {
        navigateHome({ replace: true });
      }
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? `Silme hatası: ${e.message}` : "Silme başarısız oldu");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <Layout onLogoClick={() => navigateHome({ replace: true })}>
      {error && (
        <div className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600">
          Bağlantı hatası: {error}
        </div>
      )}
      {actionError && (
        <div className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600">
          {actionError}
        </div>
      )}

      {!selectedFaceId ? (
        facesLoading
          ? <Spinner label="Yükleniyor..." />
          : (
            <FaceGrid
              faces={faces}
              onSelect={handleSelectFace}
              onMerge={handleMerge}
              onDelete={handleDelete}
              merging={merging}
              deleting={deleting}
            />
          )
      ) : facesLoading || !selectedFace || photosLoading
          ? <Spinner label="Fotoğraflar yükleniyor..." />
          : (
            <PhotoGallery
              face={selectedFace}
              photos={photos}
              onBack={() => navigateHome({ replace: true })}
            />
          )}
    </Layout>
  );
}

function Layout({ children, onLogoClick }: { children: React.ReactNode; onLogoClick: () => void }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-10 border-b border-gray-200 bg-white/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6">
          <button
            onClick={onLogoClick}
            className="flex items-center gap-3 hover:opacity-80 transition-opacity"
          >
            <img src="/logo.png" alt="DentCo Outliers" className="h-9 w-auto object-contain" />
            <div className="text-left">
              <p className="text-sm font-bold leading-tight text-gray-900">DentCo Outliers</p>
              <p className="text-xs text-gray-500">16 Mayıs 2026 · Fotoğraf Galerisi</p>
            </div>
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">{children}</main>
    </div>
  );
}

function Spinner({ label }: { label: string }) {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-3 text-gray-400">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-200 border-t-brand-500" />
      <p className="text-sm">{label}</p>
    </div>
  );
}
