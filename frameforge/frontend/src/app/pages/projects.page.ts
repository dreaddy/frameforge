import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import {
  ApiService,
  ArtStyle,
  GameProject,
  PalettePreset,
  formatApiError,
} from '../services/api.service';
import { ProjectContextService } from '../services/project-context.service';

@Component({
  selector: 'app-projects-page',
  standalone: true,
  imports: [FormsModule, RouterLink],
  template: `
    <section class="page">
      <a routerLink="/" class="back">← Gallery</a>
      <h1>Projects</h1>
      <p class="lead">
        Game projects hold creatures separately. Set name, description, and default style once —
        new generations use those defaults.
      </p>

      <div class="layout">
        <form class="form" (ngSubmit)="save()">
          <h2>{{ editingId ? 'Project settings' : 'New project' }}</h2>
          <label>
            Game name
            <input [(ngModel)]="name" name="name" placeholder="Ember Quest" required />
          </label>
          <label>
            Description
            <textarea
              [(ngModel)]="description"
              name="description"
              rows="4"
              placeholder="Tone, world, creature vibe — used when polishing prompts"
            ></textarea>
          </label>
          <label>
            Default style
            <select [(ngModel)]="defaultStyle" name="defaultStyle">
              @for (s of styles; track s.id) {
                <option [ngValue]="s.id">{{ s.label }}</option>
              }
            </select>
          </label>
          <label>
            Default size
            <select [(ngModel)]="defaultPixelSize" name="defaultPixelSize">
              <option [ngValue]="16">16</option>
              <option [ngValue]="32">32</option>
              <option [ngValue]="48">48</option>
              <option [ngValue]="64">64</option>
              <option [ngValue]="128">128</option>
              <option [ngValue]="256">256</option>
              <option [ngValue]="512">512</option>
              <option [ngValue]="768">768</option>
              <option [ngValue]="1024">1024</option>
            </select>
          </label>
          <label class="check">
            <input type="checkbox" [(ngModel)]="defaultDropShadow" name="defaultDropShadow" />
            Default drop shadow
          </label>
          @if (defaultStyle === 'pixel_art') {
            <label class="check">
              <input type="checkbox" [(ngModel)]="defaultOutline" name="defaultOutline" />
              Default pixel outline
            </label>
          }
          <label>
            Color palette
            <select
              [(ngModel)]="palettePreset"
              name="palettePreset"
              (ngModelChange)="onPresetChange($event)"
            >
              @for (p of palettePresets; track p.id) {
                <option [ngValue]="p.id">{{ p.label }}</option>
              }
              <option [ngValue]="'custom'">Custom…</option>
            </select>
          </label>
          @if (palettePresetBlurb) {
            <p class="muted palette-blurb">{{ palettePresetBlurb }}</p>
          }
          @if (palettePreset !== 'none' && paletteColors.length) {
            <div class="palette-preview">
              <button
                type="button"
                class="preview-toggle"
                (click)="palettePreviewOpen = !palettePreviewOpen"
                [attr.aria-expanded]="palettePreviewOpen"
              >
                <span class="preview-strip" aria-hidden="true">
                  @for (c of paletteColors.slice(0, 8); track c) {
                    <span class="swatch mini" [style.background]="c"></span>
                  }
                  @if (paletteColors.length > 8) {
                    <span class="more">+{{ paletteColors.length - 8 }}</span>
                  }
                </span>
                <span class="preview-label">
                  {{ paletteColors.length }} colors
                  <span class="chevron">{{ palettePreviewOpen ? '▾' : '▸' }}</span>
                </span>
              </button>
              @if (palettePreviewOpen) {
                <div class="swatches" aria-label="Palette preview">
                  @for (c of paletteColors; track c) {
                    <span
                      class="swatch"
                      [class.seed]="paletteSeedSet.has(c)"
                      [style.background]="c"
                      [title]="paletteSeedSet.has(c) ? c + ' (from images)' : c"
                    ></span>
                  }
                </div>
              }
            </div>
          }
          @if (palettePreset === 'custom') {
            <label>
              Colors <span class="optional">(hex, one per line)</span>
              <textarea
                [(ngModel)]="paletteText"
                name="paletteText"
                rows="5"
                placeholder="#1a1c2c&#10;#ef7d57&#10;…"
                (ngModelChange)="onPaletteTextChange()"
              ></textarea>
            </label>
          }
          @if (palettePreset !== 'none') {
            <div class="from-images">
              <div class="from-images-head">
                <span>From images</span>
                <span class="optional">extract colors · match presets · fill gaps</span>
              </div>
              <input
                #paletteFileInput
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif,.png,.jpg,.jpeg,.webp,.gif"
                multiple
                hidden
                (change)="onPaletteFiles($event)"
              />
              <div class="actions">
                <button
                  type="button"
                  class="btn"
                  [disabled]="busy || paletteBusy"
                  (click)="paletteFileInput.click()"
                >
                  {{ paletteBusy ? 'Reading…' : 'Upload image(s)' }}
                </button>
                @if (paletteSeed.length) {
                  <button
                    type="button"
                    class="btn"
                    [disabled]="busy || paletteBusy"
                    (click)="clearPaletteSeed()"
                  >
                    Clear image colors
                  </button>
                }
              </div>
              @if (paletteSeed.length) {
                <p class="muted palette-blurb">
                  {{ paletteSeed.length }} fixed from images
                  @if (paletteMatchLabel) {
                    · matched {{ paletteMatchLabel }}
                  }
                  @if (paletteFilledHint) {
                    · {{ paletteFilledHint }}
                  }
                  · see preview
                </p>
              }
            </div>
          }
          <div class="actions">
            <button class="btn primary" type="submit" [disabled]="busy || !name.trim()">
              {{ busy ? 'Saving…' : editingId ? 'Save settings' : 'Create project' }}
            </button>
            @if (editingId) {
              <button class="btn" type="button" (click)="resetForm()" [disabled]="busy">
                New instead
              </button>
            }
          </div>
          @if (error) {
            <p class="error">{{ error }}</p>
          }
          @if (ok) {
            <p class="ok">{{ ok }}</p>
          }
        </form>

        <aside class="list">
          <h2>Your projects</h2>
          @if (!projects.length) {
            <p class="muted">No projects yet.</p>
          } @else {
            <ul>
              @for (p of projects; track p.id) {
                <li [class.active]="p.id === activeId">
                  <button type="button" class="pick" (click)="select(p)">
                    <strong>{{ p.name }}</strong>
                    <span
                      >{{ p.character_count || 0 }} creatures
                      @if (p.trash_count) {
                        · {{ p.trash_count }} in trash
                      }
                      · {{ p.default_style }} · {{ p.default_pixel_size }}px</span
                    >
                    @if (p.description) {
                      <span class="desc">{{ p.description }}</span>
                    }
                  </button>
                  <div class="row">
                    <button type="button" class="btn" (click)="edit(p)">Edit</button>
                    <button
                      type="button"
                      class="btn danger"
                      (click)="remove(p)"
                      [disabled]="(p.character_count || 0) > 0 || (p.trash_count || 0) > 0"
                      [title]="
                        (p.character_count || 0) > 0 || (p.trash_count || 0) > 0
                          ? 'Empty creatures and trash first'
                          : 'Delete empty project'
                      "
                    >
                      Delete
                    </button>
                  </div>
                </li>
              }
            </ul>
          }
        </aside>
      </div>
    </section>
  `,
  styles: [
    `
      .page {
        padding: 2.5rem 0 4rem;
      }
      .back {
        color: var(--muted);
        text-decoration: none;
      }
      h1 {
        font-family: var(--font-display);
        font-size: 2.6rem;
        margin: 0.8rem 0 0.4rem;
      }
      h2 {
        font-family: var(--font-display);
        font-size: 1.35rem;
        margin: 0 0 0.75rem;
      }
      .lead {
        color: var(--muted);
        max-width: 40rem;
      }
      .layout {
        display: grid;
        grid-template-columns: minmax(0, 22rem) minmax(0, 1fr);
        gap: 2rem;
        margin-top: 1.5rem;
        align-items: start;
      }
      @media (max-width: 800px) {
        .layout {
          grid-template-columns: 1fr;
        }
      }
      .form {
        display: grid;
        gap: 1rem;
        background: rgba(0, 0, 0, 0.22);
        border: 1px solid rgba(255, 255, 255, 0.08);
        padding: 1.25rem;
      }
      label {
        display: grid;
        gap: 0.4rem;
        font-size: 0.9rem;
      }
      input,
      textarea,
      select {
        background: rgba(0, 0, 0, 0.28);
        border: 1px solid rgba(255, 255, 255, 0.1);
        color: var(--ink);
        padding: 0.7rem 0.8rem;
        font: inherit;
      }
      .check {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        grid-template-columns: none;
      }
      .check input {
        width: auto;
        padding: 0;
      }
      .optional {
        color: var(--muted);
        font-weight: 400;
      }
      .palette-blurb {
        margin: -0.35rem 0 0;
        font-size: 0.85rem;
      }
      .palette-preview {
        display: grid;
        gap: 0.55rem;
      }
      .preview-toggle {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        width: 100%;
        background: rgba(0, 0, 0, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.1);
        color: inherit;
        padding: 0.45rem 0.6rem;
        font: inherit;
        cursor: pointer;
        text-align: left;
      }
      .preview-toggle:hover {
        border-color: rgba(255, 196, 120, 0.35);
      }
      .preview-strip {
        display: flex;
        align-items: center;
        gap: 0.2rem;
        min-width: 0;
      }
      .swatch.mini {
        width: 0.85rem;
        height: 0.85rem;
        flex: 0 0 auto;
      }
      .preview-strip .more {
        color: var(--muted);
        font-size: 0.75rem;
        margin-left: 0.2rem;
      }
      .preview-label {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        color: var(--muted);
        font-size: 0.85rem;
        white-space: nowrap;
      }
      .chevron {
        color: var(--ink);
      }
      .swatches {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
        align-items: center;
        min-height: 1.6rem;
      }
      .swatch {
        width: 1.35rem;
        height: 1.35rem;
        border: 1px solid rgba(255, 255, 255, 0.2);
        box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.25);
      }
      .swatch.seed {
        outline: 2px solid rgba(255, 196, 120, 0.75);
        outline-offset: 1px;
      }
      .from-images {
        display: grid;
        gap: 0.55rem;
        padding: 0.75rem 0 0;
        border-top: 1px solid rgba(255, 255, 255, 0.06);
      }
      .from-images-head {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        align-items: baseline;
        font-size: 0.9rem;
      }
      .actions {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
      }
      .error {
        color: #ff8f8f;
        margin: 0;
      }
      .ok {
        color: #7dcea0;
        margin: 0;
      }
      .muted {
        color: var(--muted);
      }
      .list ul {
        list-style: none;
        margin: 0;
        padding: 0;
        display: grid;
        gap: 0.75rem;
      }
      .list li {
        background: rgba(0, 0, 0, 0.22);
        border: 1px solid rgba(255, 255, 255, 0.08);
        padding: 0.85rem;
        display: grid;
        gap: 0.65rem;
      }
      .list li.active {
        border-color: rgba(255, 196, 120, 0.4);
      }
      .pick {
        background: none;
        border: 0;
        color: inherit;
        text-align: left;
        padding: 0;
        cursor: pointer;
        display: grid;
        gap: 0.25rem;
        font: inherit;
      }
      .pick span {
        color: var(--muted);
        font-size: 0.85rem;
      }
      .desc {
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
      }
      .row {
        display: flex;
        gap: 0.5rem;
      }
      .btn.danger {
        color: #ff8f8f;
      }
    `,
  ],
})
export class ProjectsPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly ctx = inject(ProjectContextService);

  projects: GameProject[] = [];
  styles: ArtStyle[] = [];
  palettePresets: PalettePreset[] = [];
  activeId: string | null = null;
  editingId: string | null = null;
  name = '';
  description = '';
  defaultStyle = 'pixel_art';
  defaultPixelSize: 16 | 32 | 48 | 64 | 128 | 256 | 512 | 768 | 1024 = 128;
  defaultDropShadow = false;
  defaultOutline = false;
  palettePreset = 'none';
  paletteText = '';
  /** Fixed colors from reference images; further uploads merge into this. */
  paletteSeed: string[] = [];
  paletteMatchLabel = '';
  paletteFilledHint = '';
  palettePreviewOpen = false;
  busy = false;
  paletteBusy = false;
  error = '';
  ok = '';

  get paletteColors(): string[] {
    return this.parsePaletteText(this.paletteText);
  }

  get paletteSeedSet(): Set<string> {
    return new Set(this.paletteSeed.map((c) => c.toLowerCase()));
  }

  get palettePresetBlurb(): string {
    if (this.palettePreset === 'custom') {
      return 'Custom hex list — used in prompts; snap with “Apply palette”.';
    }
    return this.palettePresets.find((p) => p.id === this.palettePreset)?.blurb || '';
  }

  ngOnInit(): void {
    this.api.styles().subscribe({
      next: (res) => (this.styles = res.styles || []),
      error: () => {
        this.styles = [{ id: 'pixel_art', label: 'Pixel art', blurb: '', resize: 'nearest' }];
      },
    });
    this.api.palettePresets().subscribe({
      next: (res) => {
        this.palettePresets = (res.presets || []).filter((p) => p.id !== 'custom');
      },
      error: () => {
        this.palettePresets = [
          { id: 'none', label: 'None (unrestricted)', blurb: '', colors: [] },
        ];
      },
    });
    void this.reload();
  }

  async reload(): Promise<void> {
    await this.ctx.refresh();
    this.projects = this.ctx.projects;
    this.activeId = this.ctx.activeProjectId;
  }

  select(p: GameProject): void {
    this.ctx.setActiveProjectId(p.id);
    this.activeId = p.id;
  }

  edit(p: GameProject): void {
    this.editingId = p.id;
    this.name = p.name;
    this.description = p.description || '';
    this.defaultStyle = p.default_style || 'pixel_art';
    this.defaultPixelSize = (p.default_pixel_size as 16 | 32 | 48 | 64 | 128 | 256 | 512 | 768 | 1024) || 128;
    this.defaultDropShadow = !!p.default_drop_shadow;
    this.defaultOutline = !!p.default_outline;
    this.palettePreset = p.palette_preset || 'none';
    this.paletteText = (p.palette || []).join('\n');
    this.paletteSeed = [...(p.palette_seed || [])];
    this.paletteMatchLabel =
      this.palettePreset !== 'none' && this.palettePreset !== 'custom'
        ? this.palettePresets.find((x) => x.id === this.palettePreset)?.label || this.palettePreset
        : '';
    this.paletteFilledHint = '';
    this.palettePreviewOpen = false;
    this.error = '';
    this.ok = '';
  }

  resetForm(): void {
    this.editingId = null;
    this.name = '';
    this.description = '';
    this.defaultStyle = 'pixel_art';
    this.defaultPixelSize = 128;
    this.defaultDropShadow = false;
    this.defaultOutline = false;
    this.palettePreset = 'none';
    this.paletteText = '';
    this.paletteSeed = [];
    this.paletteMatchLabel = '';
    this.paletteFilledHint = '';
    this.palettePreviewOpen = false;
    this.error = '';
    this.ok = '';
  }

  onPresetChange(id: string): void {
    if (id === 'custom') {
      return;
    }
    const preset = this.palettePresets.find((p) => p.id === id);
    this.paletteText = (preset?.colors || []).join('\n');
    // Named preset overrides image-derived seeds
    this.paletteSeed = [];
    this.paletteMatchLabel = id === 'none' ? '' : preset?.label || '';
    this.paletteFilledHint = '';
    this.palettePreviewOpen = false;
  }

  onPaletteTextChange(): void {
    // Editing hex while on Custom stays on Custom (don't jump to a named preset).
    const colors = this.paletteColors;
    const match = this.palettePresets.find(
      (p) =>
        p.id !== 'none' &&
        p.colors.length === colors.length &&
        p.colors.every((c, i) => c.toLowerCase() === colors[i])
    );
    this.paletteMatchLabel = match?.label || '';
    this.palettePreset = 'custom';
  }

  clearPaletteSeed(): void {
    this.paletteSeed = [];
    this.paletteMatchLabel = '';
    this.paletteFilledHint = '';
  }

  async onPaletteFiles(ev: Event): Promise<void> {
    const input = ev.target as HTMLInputElement;
    const files = Array.from(input.files || []);
    input.value = '';
    if (!files.length) {
      return;
    }
    this.paletteBusy = true;
    this.error = '';
    this.ok = '';
    try {
      const existingSeed = this.paletteSeed.length ? this.paletteSeed : this.paletteColors;
      const res = await firstValueFrom(this.api.paletteFromImages(files, existingSeed));
      this.paletteSeed = res.seed || [];
      this.paletteText = (res.colors || []).join('\n');
      // Stay on Custom so the editor stays visible (match is only a hint).
      this.palettePreset = 'custom';
      this.paletteMatchLabel = res.matched_preset?.label || '';
      const filled = res.filled_count || 0;
      this.paletteFilledHint = filled > 0 ? `${filled} filled in` : '';
      this.palettePreviewOpen = true;
      const n = res.image_count || files.length;
      this.ok = res.matched_preset
        ? `Palette from ${n} image(s) → looks like ${res.matched_preset.label}.`
        : `Palette from ${n} image(s): ${this.paletteSeed.length} fixed` +
          (filled ? `, ${filled} filled` : '') +
          '.';
    } catch (e) {
      this.error = formatApiError(e, 'Could not read palette from images');
    } finally {
      this.paletteBusy = false;
    }
  }

  private parsePaletteText(text: string): string[] {
    const out: string[] = [];
    const seen = new Set<string>();
    for (const raw of String(text || '').split(/[\s,;]+/)) {
      const m = raw.trim().match(/^#?([0-9a-fA-F]{6})$/);
      if (!m) {
        continue;
      }
      const hex = `#${m[1].toLowerCase()}`;
      if (seen.has(hex)) {
        continue;
      }
      seen.add(hex);
      out.push(hex);
    }
    return out;
  }

  async save(): Promise<void> {
    if (!this.name.trim()) {
      return;
    }
    this.busy = true;
    this.error = '';
    this.ok = '';
    try {
      const colors = this.paletteColors;
      const body = {
        name: this.name.trim(),
        description: this.description.trim(),
        default_style: this.defaultStyle,
        default_pixel_size: this.defaultPixelSize,
        default_drop_shadow: this.defaultDropShadow,
        default_outline: this.defaultStyle === 'pixel_art' && this.defaultOutline,
        palette_preset: this.palettePreset === 'custom' ? 'custom' : this.palettePreset,
        palette: colors,
        palette_seed: this.paletteSeed,
      };
      let saved: GameProject;
      if (this.editingId) {
        saved = await firstValueFrom(this.api.updateProject(this.editingId, body));
        this.ok = 'Settings saved.';
      } else {
        saved = await firstValueFrom(this.api.createProject(body));
        this.ok = 'Project created.';
        this.ctx.setActiveProjectId(saved.id);
        this.editingId = saved.id;
      }
      await this.reload();
    } catch (e) {
      this.error = formatApiError(e);
    } finally {
      this.busy = false;
    }
  }

  async remove(p: GameProject): Promise<void> {
    if ((p.character_count || 0) > 0) {
      return;
    }
    if (!confirm(`Delete project “${p.name}”?`)) {
      return;
    }
    this.error = '';
    try {
      await firstValueFrom(this.api.deleteProject(p.id));
      if (this.editingId === p.id) {
        this.resetForm();
      }
      await this.reload();
    } catch (e) {
      this.error = formatApiError(e);
    }
  }
}
