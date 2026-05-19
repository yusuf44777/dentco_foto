import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Face, Photo } from "../types";

export function useFaces() {
  const [faces, setFaces] = useState<Face[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    return api.faces.list()
      .then(setFaces)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { faces, loading, error, reload };
}

export function useFacePhotos(faceId: string | null) {
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!faceId) return;
    setLoading(true);
    api.faces.photos(faceId)
      .then(setPhotos)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [faceId]);

  return { photos, loading, error };
}
