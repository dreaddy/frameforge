import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';

export interface Health {
  ok: boolean;
  comfy: { ok: boolean; error?: string };
  ollama: { ok: boolean; models?: string[]; error?: string };
}

export interface ArtStyle {
  id: string;
  label: string;
  blurb: string;
  resize: 'nearest' | 'lanczos' | string;
}

export type SourceImage = 'base' | 'standing';

export interface StandingVersion {
  id: string;
  ref?: number;
  label?: string;
  pose?: string | null;
  created_at?: string;
  preview_url?: string | null;
  files?: Record<string, string>;
}

export type ArtPurpose = 'portrait' | 'inventory' | 'showcase' | 'scene';

export type ArtSize = 512 | 768 | 1024 | 1280;

export interface ArtSizeOption {
  id: ArtSize;
  label: string;
}

export interface ArtVersion {
  id: string;
  ref?: number;
  label?: string;
  style?: string;
  purpose?: ArtPurpose | string;
  size?: number | null;
  prompt?: string | null;
  background?: string | null;
  created_at?: string;
  preview_url?: string | null;
  files?: Record<string, string>;
}

export interface PalettePreset {
  id: string;
  label: string;
  blurb: string;
  colors: string[];
}

export interface GameProject {
  id: string;
  name: string;
  description: string;
  default_style: string;
  default_pixel_size: 16 | 32 | 48 | 64 | 128 | 256 | number;
  default_drop_shadow?: boolean;
  default_outline?: boolean;
  palette_preset?: string;
  palette?: string[];
  /** Fixed colors extracted from reference images (before fill/match). */
  palette_seed?: string[];
  created_at: string;
  updated_at?: string;
  character_count?: number;
  trash_count?: number;
  item_count?: number;
  items_trash_count?: number;
}

export interface PaletteFromImagesResult {
  seed: string[];
  colors: string[];
  palette_preset: string;
  matched_preset: { id: string; label: string; score: number; coverage: number } | null;
  filled_count: number;
  extracted?: string[];
  image_count?: number;
}

export interface Character {
  id: string;
  /** Short numeric id for MCP / verbal lookup (“object 3294”). */
  ref?: number;
  project_id?: string;
  name: string;
  prompt: string;
  pixel_size: number;
  style?: string;
  drop_shadow?: boolean;
  outline?: boolean;
  created_at: string;
  base_url: string;
  preview_url?: string;
  standing_url?: string | null;
  has_standing?: boolean;
  source_image?: SourceImage;
  active_standing_id?: string | null;
  standing_versions?: StandingVersion[];
  art_versions?: ArtVersion[];
  animations?: Record<string, AnimationMeta>;
  animation_ids?: string[];
  trash?: CharacterTrash;
}

/** Item asset — same core shape as Character, without standing/poses. */
export interface Item {
  id: string;
  /** Short numeric id for MCP / verbal lookup (“object 3294”). */
  ref?: number;
  kind?: 'item';
  project_id?: string;
  name: string;
  prompt: string;
  pixel_size: number;
  style?: string;
  drop_shadow?: boolean;
  outline?: boolean;
  created_at: string;
  base_url: string;
  preview_url?: string;
  art_versions?: ArtVersion[];
  animations?: Record<string, AnimationMeta>;
  animation_ids?: string[];
  trash?: ItemTrash;
}

export interface TrashedItem {
  id: string;
  ref?: number;
  project_id?: string;
  name: string;
  style?: string;
  pixel_size?: number;
  created_at?: string;
  deleted_at?: string;
  preview_url?: string;
  base_url?: string;
}

export interface ItemTrash {
  animations?: Record<string, TrashedAnimation>;
  art?: TrashedArt[];
}

export interface TrashedCharacter {
  id: string;
  ref?: number;
  project_id?: string;
  name: string;
  style?: string;
  pixel_size?: number;
  created_at?: string;
  deleted_at?: string;
  preview_url?: string;
  base_url?: string;
}

export interface CharacterTrash {
  animations?: Record<string, TrashedAnimation>;
  standing?: TrashedStanding[];
  art?: TrashedArt[];
}

export interface TrashedAnimation extends AnimationMeta {
  deleted_at?: string;
}

export interface TrashedStanding {
  id: string;
  kind?: string;
  deleted_at?: string;
  preview_url?: string | null;
  files?: Record<string, string>;
}

export interface TrashedArt {
  id: string;
  kind?: string;
  deleted_at?: string;
  label?: string;
  style?: string;
  purpose?: string;
  size?: number | null;
  preview_url?: string | null;
  files?: Record<string, string>;
}

export interface AnimationMeta {
  id: string;
  ref?: number;
  type: string;
  name?: string;
  fps: number;
  frames: number;
  variants: VariantMeta[];
  selected_variant: number | null;
  motion_notes?: string;
}

export interface VariantMeta {
  index: number;
  method: string;
  frame_urls: string[];
  video_url?: string;
  source_image?: SourceImage;
  stance_url?: string;
}

export interface JobStatus {
  id: string;
  kind: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress: number;
  message: string;
  character_id?: string;
  item_id?: string;
  animation_id?: string;
  error?: string;
  result?: Record<string, unknown>;
}

/** Readable message from HttpClient / unknown throwables (avoids "[object Object]"). */
export function formatApiError(err: unknown, fallback = 'Request failed'): string {
  if (err == null) {
    return fallback;
  }
  if (typeof err === 'string') {
    return err;
  }
  if (err instanceof Error && err.message && err.message !== '[object Object]') {
    const anyErr = err as Error & { error?: unknown; status?: number };
    const fromBody = formatErrorBody(anyErr.error);
    if (fromBody) {
      return anyErr.status ? `${anyErr.status}: ${fromBody}` : fromBody;
    }
    return err.message;
  }
  if (typeof err === 'object') {
    const o = err as { error?: unknown; message?: unknown; detail?: unknown; status?: number };
    const fromBody = formatErrorBody(o.error ?? o.detail ?? o);
    if (fromBody) {
      return o.status ? `${o.status}: ${fromBody}` : fromBody;
    }
    if (typeof o.message === 'string' && o.message !== '[object Object]') {
      return o.message;
    }
  }
  return fallback;
}

function formatErrorBody(body: unknown): string {
  if (body == null) {
    return '';
  }
  if (typeof body === 'string') {
    return body;
  }
  if (typeof body === 'object') {
    const o = body as { detail?: unknown; message?: unknown; error?: unknown };
    if (typeof o.detail === 'string') {
      return o.detail;
    }
    if (Array.isArray(o.detail)) {
      return o.detail
        .map((d) => {
          if (typeof d === 'string') {
            return d;
          }
          if (d && typeof d === 'object' && 'msg' in d) {
            return String((d as { msg: unknown }).msg);
          }
          return JSON.stringify(d);
        })
        .join('; ');
    }
    if (typeof o.message === 'string') {
      return o.message;
    }
    if (typeof o.error === 'string') {
      return o.error;
    }
    try {
      return JSON.stringify(body);
    } catch {
      return '';
    }
  }
  return String(body);
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api';

  health(): Observable<Health> {
    return this.http.get<Health>(`${this.base}/health`);
  }

  presets(): Observable<{ presets: Record<string, string> }> {
    return this.http.get<{ presets: Record<string, string> }>(`${this.base}/presets/animations`);
  }

  itemPresets(): Observable<{ presets: Record<string, string>; default?: string }> {
    return this.http.get<{ presets: Record<string, string>; default?: string }>(
      `${this.base}/presets/animations/items`
    );
  }

  styles(): Observable<{ styles: ArtStyle[]; default: string }> {
    return this.http.get<{ styles: ArtStyle[]; default: string }>(`${this.base}/presets/styles`);
  }

  palettePresets(): Observable<{ presets: PalettePreset[]; default: string }> {
    return this.http.get<{ presets: PalettePreset[]; default: string }>(
      `${this.base}/presets/palettes`
    );
  }

  paletteFromImages(files: File[], existingSeed: string[] = []) {
    const fd = new FormData();
    for (const f of files) {
      fd.append('files', f, f.name);
    }
    if (existingSeed.length) {
      fd.append('seed', existingSeed.join(' '));
    }
    return this.http.post<PaletteFromImagesResult>(`${this.base}/presets/palettes/from-images`, fd);
  }

  artSizes(): Observable<{ sizes: ArtSizeOption[]; default: ArtSize }> {
    return this.http.get<{ sizes: ArtSizeOption[]; default: ArtSize }>(
      `${this.base}/presets/art-sizes`
    );
  }

  listProjects(): Observable<GameProject[]> {
    return this.http.get<GameProject[]>(`${this.base}/projects`);
  }

  getProject(id: string): Observable<GameProject> {
    return this.http.get<GameProject>(`${this.base}/projects/${id}`);
  }

  createProject(body: {
    name: string;
    description?: string;
    default_style?: string;
    default_pixel_size?: number;
    default_drop_shadow?: boolean;
    default_outline?: boolean;
    palette_preset?: string;
    palette?: string[];
    palette_seed?: string[];
  }): Observable<GameProject> {
    return this.http.post<GameProject>(`${this.base}/projects`, body);
  }

  updateProject(
    id: string,
    body: {
      name?: string;
      description?: string;
      default_style?: string;
      default_pixel_size?: number;
      default_drop_shadow?: boolean;
      default_outline?: boolean;
      palette_preset?: string;
      palette?: string[];
      palette_seed?: string[];
    }
  ): Observable<GameProject> {
    return this.http.put<GameProject>(`${this.base}/projects/${id}`, body);
  }

  applyCharacterPalette(characterId: string, includeAnimations = true) {
    return this.http.post<{
      ok: boolean;
      palette: string[];
      counts: Record<string, number>;
      character: Character;
    }>(`${this.base}/characters/${characterId}/apply-palette`, {
      include_animations: includeAnimations,
    });
  }

  applyItemPalette(itemId: string, includeAnimations = true) {
    return this.http.post<{
      ok: boolean;
      palette: string[];
      counts: Record<string, number>;
      item: Item;
    }>(`${this.base}/items/${itemId}/apply-palette`, {
      include_animations: includeAnimations,
    });
  }

  deleteProject(id: string): Observable<{ ok: boolean }> {
    return this.http.delete<{ ok: boolean }>(`${this.base}/projects/${id}`);
  }

  listCharacters(projectId?: string | null): Observable<Character[]> {
    const q = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
    return this.http.get<Character[]>(`${this.base}/characters${q}`);
  }

  listTrashedCharacters(projectId?: string | null): Observable<TrashedCharacter[]> {
    const q = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
    return this.http.get<TrashedCharacter[]>(`${this.base}/characters/trash${q}`);
  }

  trashCharacter(id: string): Observable<{ ok: boolean; trashed: TrashedCharacter }> {
    return this.http.delete<{ ok: boolean; trashed: TrashedCharacter }>(
      `${this.base}/characters/${id}`
    );
  }

  restoreCharacter(id: string): Observable<{ ok: boolean; character: Character }> {
    return this.http.post<{ ok: boolean; character: Character }>(
      `${this.base}/characters/${id}/restore`,
      {}
    );
  }

  getCharacter(id: string): Observable<Character> {
    return this.http.get<Character>(`${this.base}/characters/${id}`);
  }

  polishPrompt(
    prompt: string,
    style: string,
    outline = false,
    projectId?: string | null,
    subject: 'character' | 'item' = 'character'
  ): Observable<{ prompt: string; source: 'ollama' | 'fallback'; style: string }> {
    return this.http.post<{ prompt: string; source: 'ollama' | 'fallback'; style: string }>(
      `${this.base}/prompts/polish`,
      { prompt, style, outline, project_id: projectId ?? null, subject }
    );
  }

  createCharacter(body: {
    prompt: string;
    name?: string;
    project_id?: string | null;
    pixel_size: number;
    style?: string;
    drop_shadow?: boolean;
    outline?: boolean;
    polish_prompt?: boolean;
  }): Observable<{ job_id: string; character_id: string }> {
    return this.http.post<{ job_id: string; character_id: string }>(`${this.base}/characters`, {
      ...body,
      polish_prompt: body.polish_prompt ?? false,
      drop_shadow: body.drop_shadow ?? false,
      outline: body.outline ?? false,
    });
  }

  createCharacterFromImage(body: {
    file: Blob;
    filename?: string;
    mode: 'upload' | 'img2img';
    name?: string;
    project_id?: string | null;
    pixel_size: number;
    style?: string;
    drop_shadow?: boolean;
    outline?: boolean;
    prompt?: string;
    key_background?: boolean;
    auto_crop?: boolean;
    denoise?: number | null;
    polish_prompt?: boolean;
  }): Observable<{ job_id: string; character_id: string }> {
    const fd = new FormData();
    fd.append('file', body.file, body.filename || 'crop.png');
    fd.append('mode', body.mode);
    fd.append('name', body.name || 'Creature');
    fd.append('pixel_size', String(body.pixel_size));
    fd.append('style', body.style || 'pixel_art');
    fd.append('drop_shadow', String(!!body.drop_shadow));
    fd.append('outline', String(!!body.outline));
    fd.append('prompt', body.prompt || '');
    fd.append('key_background', String(body.key_background ?? true));
    fd.append('auto_crop', String(body.auto_crop ?? true));
    fd.append('polish_prompt', String(!!body.polish_prompt));
    if (body.project_id) {
      fd.append('project_id', body.project_id);
    }
    if (body.denoise != null) {
      fd.append('denoise', String(body.denoise));
    }
    return this.http.post<{ job_id: string; character_id: string }>(
      `${this.base}/characters/from-image`,
      fd
    );
  }

  prepareStanding(
    characterId: string,
    setAsSource = true,
    pose = 'standing'
  ): Observable<{ job_id: string }> {
    return this.http.post<{ job_id: string }>(
      `${this.base}/characters/${characterId}/standing`,
      { set_as_source: setAsSource, pose }
    );
  }

  generateArt(
    characterId: string,
    body: {
      style: string;
      purpose: ArtPurpose;
      size?: ArtSize;
      background?: string | null;
      prompt?: string | null;
    }
  ): Observable<{ job_id: string }> {
    return this.http.post<{ job_id: string }>(
      `${this.base}/characters/${characterId}/art`,
      body
    );
  }

  deleteArt(characterId: string, artId: string) {
    return this.http.delete<{ ok: boolean }>(
      `${this.base}/characters/${characterId}/art/${artId}`
    );
  }

  restoreArt(characterId: string, trashId: string) {
    return this.http.post<{ ok: boolean; character?: Character }>(
      `${this.base}/characters/${characterId}/trash/art/${trashId}/restore`,
      {}
    );
  }

  setSourceImage(
    characterId: string,
    sourceImage: SourceImage,
    standingId?: string | null
  ): Observable<Character> {
    return this.http.put<Character>(`${this.base}/characters/${characterId}/source-image`, {
      source_image: sourceImage,
      standing_id: standingId ?? null,
    });
  }

  createAnimation(
    characterId: string,
    body: {
      anim_type: string;
      variants: number;
      frames: number;
      fps: number;
      method: 'i2v' | 'pose_keyframes';
      source_image?: SourceImage | null;
      motion_notes?: string;
      name?: string;
    }
  ): Observable<{ job_id: string }> {
    return this.http.post<{ job_id: string }>(
      `${this.base}/characters/${characterId}/animations`,
      body
    );
  }

  updateAnimation(
    characterId: string,
    animationId: string,
    body: { name?: string; fps?: number }
  ) {
    return this.http.patch<AnimationMeta>(
      `${this.base}/characters/${characterId}/animations/${animationId}`,
      body
    );
  }

  renameAnimation(characterId: string, animationId: string, name: string) {
    return this.updateAnimation(characterId, animationId, { name });
  }

  job(jobId: string): Observable<JobStatus> {
    return this.http.get<JobStatus>(`${this.base}/jobs/${jobId}`);
  }

  async waitJob(jobId: string, onTick?: (j: JobStatus) => void): Promise<JobStatus> {
    for (;;) {
      const j = await firstValueFrom(this.job(jobId));
      onTick?.(j);
      if (j.status === 'completed' || j.status === 'failed') {
        return j;
      }
      await firstValueFrom(timer(1500));
    }
  }

  selectVariant(characterId: string, animationId: string, variantIndex: number | null) {
    return this.http.post(
      `${this.base}/characters/${characterId}/animations/${animationId}/select-variant`,
      { variant_index: variantIndex }
    );
  }

  deleteAnimation(characterId: string, animationId: string) {
    return this.http.delete<{ ok: boolean }>(
      `${this.base}/characters/${characterId}/animations/${animationId}`
    );
  }

  restoreAnimation(characterId: string, animationId: string) {
    return this.http.post<{ ok: boolean }>(
      `${this.base}/characters/${characterId}/trash/animations/${animationId}/restore`,
      {}
    );
  }

  deleteStanding(characterId: string, standingId?: string | null) {
    const q = standingId ? `?standing_id=${encodeURIComponent(standingId)}` : '';
    return this.http.delete<{ ok: boolean }>(
      `${this.base}/characters/${characterId}/standing${q}`
    );
  }

  restoreStanding(characterId: string, trashId: string) {
    return this.http.post<{ ok: boolean; character?: Character }>(
      `${this.base}/characters/${characterId}/trash/standing/${trashId}/restore`,
      {}
    );
  }

  exportUnity(characterId: string): Observable<{ zip_url: string; filename: string }> {
    return this.http.post<{ zip_url: string; filename: string }>(
      `${this.base}/characters/${characterId}/export/unity`,
      {}
    );
  }

  listItems(projectId?: string | null): Observable<Item[]> {
    const q = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
    return this.http.get<Item[]>(`${this.base}/items${q}`);
  }

  listTrashedItems(projectId?: string | null): Observable<TrashedItem[]> {
    const q = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
    return this.http.get<TrashedItem[]>(`${this.base}/items/trash${q}`);
  }

  trashItem(id: string): Observable<{ ok: boolean; trashed: TrashedItem }> {
    return this.http.delete<{ ok: boolean; trashed: TrashedItem }>(`${this.base}/items/${id}`);
  }

  restoreItem(id: string): Observable<{ ok: boolean; item: Item }> {
    return this.http.post<{ ok: boolean; item: Item }>(`${this.base}/items/${id}/restore`, {});
  }

  getItem(id: string): Observable<Item> {
    return this.http.get<Item>(`${this.base}/items/${id}`);
  }

  createItem(body: {
    prompt: string;
    name?: string;
    project_id?: string | null;
    pixel_size: number;
    style?: string;
    drop_shadow?: boolean;
    outline?: boolean;
    polish_prompt?: boolean;
  }): Observable<{ job_id: string; item_id: string }> {
    return this.http.post<{ job_id: string; item_id: string }>(`${this.base}/items`, {
      ...body,
      polish_prompt: body.polish_prompt ?? false,
      drop_shadow: body.drop_shadow ?? false,
      outline: body.outline ?? false,
    });
  }

  createItemFromImage(body: {
    file: Blob;
    filename?: string;
    mode: 'upload' | 'img2img';
    name?: string;
    project_id?: string | null;
    pixel_size: number;
    style?: string;
    drop_shadow?: boolean;
    outline?: boolean;
    prompt?: string;
    key_background?: boolean;
    auto_crop?: boolean;
    denoise?: number | null;
    polish_prompt?: boolean;
  }): Observable<{ job_id: string; item_id: string }> {
    const fd = new FormData();
    fd.append('file', body.file, body.filename || 'crop.png');
    fd.append('mode', body.mode);
    fd.append('name', body.name || 'Item');
    fd.append('pixel_size', String(body.pixel_size));
    fd.append('style', body.style || 'pixel_art');
    fd.append('drop_shadow', String(!!body.drop_shadow));
    fd.append('outline', String(!!body.outline));
    fd.append('prompt', body.prompt || '');
    fd.append('key_background', String(body.key_background ?? true));
    fd.append('auto_crop', String(body.auto_crop ?? true));
    fd.append('polish_prompt', String(!!body.polish_prompt));
    if (body.project_id) {
      fd.append('project_id', body.project_id);
    }
    if (body.denoise != null) {
      fd.append('denoise', String(body.denoise));
    }
    return this.http.post<{ job_id: string; item_id: string }>(`${this.base}/items/from-image`, fd);
  }

  generateItemArt(
    itemId: string,
    body: {
      style: string;
      purpose: ArtPurpose;
      size?: ArtSize;
      background?: string | null;
      prompt?: string | null;
    }
  ): Observable<{ job_id: string }> {
    return this.http.post<{ job_id: string }>(`${this.base}/items/${itemId}/art`, body);
  }

  deleteItemArt(itemId: string, artId: string) {
    return this.http.delete<{ ok: boolean }>(`${this.base}/items/${itemId}/art/${artId}`);
  }

  restoreItemArt(itemId: string, trashId: string) {
    return this.http.post<{ ok: boolean; item?: Item }>(
      `${this.base}/items/${itemId}/trash/art/${trashId}/restore`,
      {}
    );
  }

  createItemAnimation(
    itemId: string,
    body: {
      anim_type: string;
      variants: number;
      frames: number;
      fps: number;
      method: 'i2v' | 'pose_keyframes';
      motion_notes?: string;
      name?: string;
    }
  ): Observable<{ job_id: string }> {
    return this.http.post<{ job_id: string }>(`${this.base}/items/${itemId}/animations`, body);
  }

  updateItemAnimation(itemId: string, animationId: string, body: { name?: string; fps?: number }) {
    return this.http.patch<AnimationMeta>(
      `${this.base}/items/${itemId}/animations/${animationId}`,
      body
    );
  }

  renameItemAnimation(itemId: string, animationId: string, name: string) {
    return this.updateItemAnimation(itemId, animationId, { name });
  }

  selectItemVariant(itemId: string, animationId: string, variantIndex: number | null) {
    return this.http.post(
      `${this.base}/items/${itemId}/animations/${animationId}/select-variant`,
      { variant_index: variantIndex }
    );
  }

  deleteItemAnimation(itemId: string, animationId: string) {
    return this.http.delete<{ ok: boolean }>(
      `${this.base}/items/${itemId}/animations/${animationId}`
    );
  }

  restoreItemAnimation(itemId: string, animationId: string) {
    return this.http.post<{ ok: boolean }>(
      `${this.base}/items/${itemId}/trash/animations/${animationId}/restore`,
      {}
    );
  }

  exportItemUnity(itemId: string): Observable<{ zip_url: string; filename: string }> {
    return this.http.post<{ zip_url: string; filename: string }>(
      `${this.base}/items/${itemId}/export/unity`,
      {}
    );
  }

  fileUrl(path: string): string {
    if (path.startsWith('http')) {
      return path;
    }
    return path.startsWith('/') ? path : `/${path}`;
  }
}
