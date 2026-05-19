import { useEffect, useState } from "react";
import { FaceGrid } from "./components/FaceGrid";
import { PhotoGallery } from "./components/PhotoGallery";
import { useFaces, useFacePhotos } from "./hooks/useEvent";
import { api } from "./lib/api";
import type { Face } from "./types";
import { LogIn, LogOut, ShieldCheck } from "lucide-react";

const FACE_ROUTE_PREFIX = "/faces/";
const ADMIN_SESSION_KEY = "dentco_admin_session";

interface AdminSession {
  token: string;
  expiresAt: number;
}

function facePath(faceId: string) {
  return `${FACE_ROUTE_PREFIX}${encodeURIComponent(faceId)}`;
}

function getFaceIdFromPath() {
  const { pathname } = window.location;
  if (!pathname.startsWith(FACE_ROUTE_PREFIX)) return null;
  const raw = pathname.slice(FACE_ROUTE_PREFIX.length).split("/")[0];
  return raw ? decodeURIComponent(raw) : null;
}

function readAdminSession(): AdminSession | null {
  try {
    const raw = window.localStorage.getItem(ADMIN_SESSION_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as AdminSession;
    if (!session.token || session.expiresAt * 1000 <= Date.now()) {
      window.localStorage.removeItem(ADMIN_SESSION_KEY);
      return null;
    }
    return session;
  } catch {
    window.localStorage.removeItem(ADMIN_SESSION_KEY);
    return null;
  }
}

export default function App() {
  const { faces, loading: facesLoading, error, reload: reloadFaces } = useFaces();
  const [selectedFaceId, setSelectedFaceId] = useState<string | null>(() => getFaceIdFromPath());
  const [routeError, setRouteError] = useState<string | null>(null);
  const [adminSession, setAdminSession] = useState<AdminSession | null>(() => readAdminSession());
  const [loginOpen, setLoginOpen] = useState(false);
  const [selectedFaceIds, setSelectedFaceIds] = useState<Set<string>>(new Set());
  const [adminActionLoading, setAdminActionLoading] = useState(false);
  const [adminActionError, setAdminActionError] = useState<string | null>(null);
  const [adminActionMessage, setAdminActionMessage] = useState<string | null>(null);
  const selectedFace = selectedFaceId
    ? faces.find((face) => face.id === selectedFaceId) ?? null
    : null;
  const selectedFaces = faces.filter((face) => selectedFaceIds.has(face.id));
  const { photos, loading: photosLoading, error: photosError } = useFacePhotos(selectedFace?.id ?? null);

  useEffect(() => {
    if (!adminSession) return;
    api.auth.session(adminSession.token).catch(() => {
      window.localStorage.removeItem(ADMIN_SESSION_KEY);
      setAdminSession(null);
      setSelectedFaceIds(new Set());
    });
  }, [adminSession]);

  useEffect(() => {
    setSelectedFaceIds((current) => {
      const validIds = new Set(faces.map((face) => face.id));
      return new Set([...current].filter((id) => validIds.has(id)));
    });
  }, [faces]);

  useEffect(() => {
    function handlePopState() {
      setSelectedFaceId(getFaceIdFromPath());
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (!selectedFaceId || facesLoading || faces.length === 0 || selectedFace) return;
    setRouteError("Bu kişi klasörü bulunamadı.");
    navigateHome({ replace: true, clearMessage: false });
  }, [faces, facesLoading, selectedFace, selectedFaceId]);

  function navigateHome({ replace = false, clearMessage = true } = {}) {
    const method = replace ? "replaceState" : "pushState";
    window.history[method]({ view: "home" }, "", "/");
    setSelectedFaceId(null);
    if (clearMessage) setRouteError(null);
  }

  function handleSelectFace(face: Face) {
    window.history.pushState({ view: "face", faceId: face.id }, "", facePath(face.id));
    setSelectedFaceId(face.id);
    setRouteError(null);
  }

  function handleLogin(session: AdminSession) {
    window.localStorage.setItem(ADMIN_SESSION_KEY, JSON.stringify(session));
    setAdminSession(session);
    setLoginOpen(false);
    setAdminActionError(null);
  }

  function handleLogout() {
    window.localStorage.removeItem(ADMIN_SESSION_KEY);
    setAdminSession(null);
    setSelectedFaceIds(new Set());
    setAdminActionMessage(null);
  }

  function handleToggleFace(faceId: string) {
    setSelectedFaceIds((current) => {
      const next = new Set(current);
      if (next.has(faceId)) {
        next.delete(faceId);
      } else {
        next.add(faceId);
      }
      return next;
    });
  }

  async function handleMergeFaces() {
    if (!adminSession || selectedFaces.length < 2 || adminActionLoading) return;
    const target = selectedFaces.reduce((best, face) =>
      face.photo_count > best.photo_count ? face : best
    );
    const sourceIds = selectedFaces
      .filter((face) => face.id !== target.id)
      .map((face) => face.id);
    const targetLabel = target.label ?? "en çok fotoğrafı olan kişi";

    if (!window.confirm(`${sourceIds.length} kişi "${targetLabel}" altında birleştirilecek. Devam edilsin mi?`)) {
      return;
    }

    setAdminActionLoading(true);
    setAdminActionError(null);
    setAdminActionMessage(null);
    try {
      await api.faces.merge(target.id, sourceIds, adminSession.token);
      setSelectedFaceIds(new Set());
      setAdminActionMessage(`${sourceIds.length} kişi başarıyla birleştirildi.`);
      await reloadFaces();
    } catch (error) {
      setAdminActionError(error instanceof Error ? error.message : "Birleştirme başarısız oldu.");
    } finally {
      setAdminActionLoading(false);
    }
  }

  async function handleDeleteFaces() {
    if (!adminSession || selectedFaces.length === 0 || adminActionLoading) return;
    const label = selectedFaces.length === 1
      ? selectedFaces[0].label ?? "seçili kişi"
      : `${selectedFaces.length} kişi`;

    if (!window.confirm(`${label} galeriden silinecek. Orijinal fotoğraflar korunur. Devam edilsin mi?`)) {
      return;
    }

    setAdminActionLoading(true);
    setAdminActionError(null);
    setAdminActionMessage(null);
    try {
      await Promise.all(selectedFaces.map((face) => api.faces.delete(face.id, adminSession.token)));
      setSelectedFaceIds(new Set());
      setAdminActionMessage(`${selectedFaces.length} kişi silindi.`);
      await reloadFaces();
    } catch (error) {
      setAdminActionError(error instanceof Error ? error.message : "Silme başarısız oldu.");
    } finally {
      setAdminActionLoading(false);
    }
  }

  return (
    <Layout
      isAdmin={Boolean(adminSession)}
      onLoginClick={() => setLoginOpen(true)}
      onLogoClick={() => navigateHome({ replace: true })}
      onLogout={handleLogout}
    >
      {error && (
        <div className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600">
          Bağlantı hatası: {error}
        </div>
      )}
      {routeError && (
        <div className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600">
          {routeError}
        </div>
      )}
      {photosError && (
        <div className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600">
          Fotoğraf yükleme hatası: {photosError}
        </div>
      )}
      {adminActionError && (
        <div className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600">
          Admin işlem hatası: {adminActionError}
        </div>
      )}
      {adminActionMessage && (
        <div className="mb-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {adminActionMessage}
        </div>
      )}

      {!selectedFaceId ? (
        facesLoading
          ? <Spinner label="Yükleniyor..." />
          : (
            <FaceGrid
              faces={faces}
              isAdmin={Boolean(adminSession)}
              selectedFaceIds={selectedFaceIds}
              actionLoading={adminActionLoading}
              onSelect={handleSelectFace}
              onToggleFace={handleToggleFace}
              onMergeSelected={handleMergeFaces}
              onDeleteSelected={handleDeleteFaces}
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
      {loginOpen && (
        <AdminLoginDialog
          onClose={() => setLoginOpen(false)}
          onLogin={handleLogin}
        />
      )}
    </Layout>
  );
}

function Layout({
  children,
  isAdmin,
  onLoginClick,
  onLogoClick,
  onLogout,
}: {
  children: React.ReactNode;
  isAdmin: boolean;
  onLoginClick: () => void;
  onLogoClick: () => void;
  onLogout: () => void;
}) {
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
          <div className="ml-auto">
            {isAdmin ? (
              <button
                type="button"
                onClick={onLogout}
                className="inline-flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-semibold text-emerald-700 transition-colors hover:bg-emerald-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2"
              >
                <ShieldCheck size={16} />
                <span className="hidden sm:inline">Admin açık</span>
                <LogOut size={16} />
              </button>
            ) : (
              <button
                type="button"
                onClick={onLoginClick}
                className="inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm font-semibold text-gray-600 shadow-sm transition-colors hover:border-brand-500 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
              >
                <LogIn size={16} />
                Admin girişi
              </button>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">{children}</main>
    </div>
  );
}

function AdminLoginDialog({
  onClose,
  onLogin,
}: {
  onClose: () => void;
  onLogin: (session: AdminSession) => void;
}) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!password.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const session = await api.auth.login(password);
      onLogin({ token: session.token, expiresAt: session.expires_at });
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Giriş başarısız oldu.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/60 px-4"
      onClick={onClose}
    >
      <form
        onSubmit={handleSubmit}
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-sm rounded-xl bg-white p-5 shadow-2xl"
      >
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-50 text-brand-600">
            <ShieldCheck size={20} />
          </div>
          <div>
            <h2 className="font-semibold text-gray-900">Admin girişi</h2>
            <p className="text-xs text-gray-500">Birleştir ve sil araçları açılır.</p>
          </div>
        </div>

        <label className="mb-2 block text-sm font-medium text-gray-700" htmlFor="admin-password">
          Şifre
        </label>
        <input
          id="admin-password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoFocus
          className="mb-3 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30"
        />

        {error && (
          <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
          >
            Vazgeç
          </button>
          <button
            type="submit"
            disabled={loading || !password.trim()}
            className="rounded-xl bg-brand-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? "Giriş yapılıyor..." : "Giriş yap"}
          </button>
        </div>
      </form>
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
