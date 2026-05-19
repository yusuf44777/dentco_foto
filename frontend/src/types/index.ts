export interface Face {
  id: string;
  avatar_url: string;
  label: string | null;
  photo_count: number;
}

export interface Photo {
  id: string;
  url: string;
  taken_at: string | null;
  bbox: {
    bbox_x: number;
    bbox_y: number;
    bbox_w: number;
    bbox_h: number;
  };
}

export interface Event {
  id: string;
  name: string;
  description: string | null;
  date: string | null;
}
