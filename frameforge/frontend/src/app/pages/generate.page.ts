import {
  AfterViewInit,
  ChangeDetectorRef,
  Component,
  OnInit,
  ViewChild,
  inject,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { SpriteImagePickerComponent } from '../components/sprite-image-picker.component';
import { LightboxDirective } from '../directives/lightbox.directive';
import { ApiService, ArtStyle, Character, Item, formatApiError } from '../services/api.service';
import { ProjectContextService } from '../services/project-context.service';

type CreateMode = 'text2img' | 'img2img' | 'upload';
type AssetKind = 'creature' | 'item';

@Component({
  selector: 'app-generate-page',
  standalone: true,
  imports: [FormsModule, RouterLink, SpriteImagePickerComponent, LightboxDirective],
  template: `
    <section class="page">
      <a routerLink="/" class="back">← Gallery</a>
      <h1>{{ pageTitle }}</h1>
      <p class="lead">
        @if (fromSourceId) {
          Recreating from an existing {{ isItem ? 'item' : 'creature' }} — image + prompt prefilled
          for another try.
        } @else if (projectLabel) {
          Saving into <strong>{{ projectLabel }}</strong>.
        }
        {{ modeBlurb }}
      </p>

      <div class="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          class="tab"
          [class.active]="mode === 'text2img'"
          [attr.aria-selected]="mode === 'text2img'"
          (click)="setMode('text2img')"
        >
          Text → Image
        </button>
        <button
          type="button"
          role="tab"
          class="tab"
          [class.active]="mode === 'img2img'"
          [attr.aria-selected]="mode === 'img2img'"
          (click)="setMode('img2img')"
        >
          Image → Image
        </button>
        <button
          type="button"
          role="tab"
          class="tab"
          [class.active]="mode === 'upload'"
          [attr.aria-selected]="mode === 'upload'"
          (click)="setMode('upload')"
        >
          Upload
        </button>
      </div>

      <div class="layout">
        <form class="form" (ngSubmit)="submit()">
          <label>
            Name
            <input
              [(ngModel)]="name"
              name="name"
              [placeholder]="isItem ? 'Frost vial' : 'Emberling'"
            />
          </label>
          <label>
            Style
            <select [(ngModel)]="style" name="style" (ngModelChange)="onStyleChange()">
              @for (s of styles; track s.id) {
                <option [ngValue]="s.id">{{ s.label }}</option>
              }
            </select>
          </label>

          @if (mode !== 'upload') {
            <label>
              Prompt
              <textarea
                [(ngModel)]="prompt"
                name="prompt"
                rows="5"
                [placeholder]="promptPlaceholder"
              ></textarea>
            </label>
            <div class="row">
              <button
                class="btn"
                type="button"
                (click)="polish()"
                [disabled]="polishing || !prompt.trim()"
              >
                {{ polishing ? 'Polishing…' : 'Polish prompt' }}
              </button>
              @if (polishSource) {
                <span class="hint">via {{ polishSource }}</span>
              }
            </div>
            @if (showPolished) {
              <label>
                Polished prompt
                <textarea
                  [(ngModel)]="polishedPrompt"
                  name="polishedPrompt"
                  rows="5"
                  placeholder="Result appears here — edit before generating"
                ></textarea>
              </label>
            }
          } @else {
            <label>
              Notes <span class="optional">(optional)</span>
              <textarea
                [(ngModel)]="prompt"
                name="prompt"
                rows="2"
                placeholder="e.g. fire horse from concept sheet"
              ></textarea>
            </label>
          }

          @if (mode !== 'text2img') {
            <div class="block">
              <span class="block-label">Source image</span>
              <app-sprite-image-picker
                #picker
                [disabled]="busy"
                (croppedChange)="onCropped($event)"
              />
            </div>
          }

          <label>
            {{ sizeLabel }}
            <select [(ngModel)]="pixelSize" name="pixelSize">
              <option [ngValue]="16">16</option>
              <option [ngValue]="32">32</option>
              <option [ngValue]="48">48 (3×3 at 16px)</option>
              <option [ngValue]="64">64</option>
              <option [ngValue]="128">128</option>
              <option [ngValue]="256">256</option>
              <option [ngValue]="512">512</option>
              <option [ngValue]="768">768</option>
              <option [ngValue]="1024">1024</option>
            </select>
          </label>

          @if (mode === 'upload') {
            <label class="check">
              <input type="checkbox" [(ngModel)]="keyBackground" name="keyBackground" />
              Remove green / flat background
            </label>
            <label class="check">
              <input type="checkbox" [(ngModel)]="autoCrop" name="autoCrop" />
              Auto-trim after key (uses your square crop either way)
            </label>
          }

          @if (mode === 'img2img') {
            <label>
              AI strength
              <input
                type="range"
                min="0.35"
                max="0.9"
                step="0.05"
                [(ngModel)]="denoise"
                name="denoise"
              />
              <span class="hint">{{ denoiseLabel }}</span>
            </label>
          }

          @if (style === 'pixel_art') {
            <label class="check">
              <input type="checkbox" [(ngModel)]="outline" name="outline" />
              Pixel outline (dark contour)
            </label>
          }
          <label class="check">
            <input type="checkbox" [(ngModel)]="dropShadow" name="dropShadow" />
            Drop shadow under sprite
          </label>

          <button class="btn primary" type="submit" [disabled]="busy || !canSubmit">
            {{ submitLabel }}
          </button>
          @if (error) {
            <p class="error">{{ error }}</p>
          }
        </form>

        <aside class="preview">
          @if (busy && !result) {
            <div class="panel empty">
              <p>{{ status || 'Working…' }}</p>
            </div>
          } @else if (result) {
            <div class="panel">
              <img
                [src]="previewUrl"
                [alt]="result.name"
                [appLightbox]="previewUrl"
                [appLightboxAlt]="result.name"
                [appLightboxCaption]="result.name + ' · ' + result.pixel_size + 'px'"
              />
              <div class="meta">
                <strong>{{ result.name }}</strong>
                <span>{{ result.style || style }} · {{ result.pixel_size }}px</span>
              </div>
              @if (result.prompt && result.prompt !== '(uploaded)') {
                <p class="used-prompt">{{ result.prompt }}</p>
              }
              <div class="actions">
                <button class="btn primary" type="button" (click)="continueAnimate()" [disabled]="busy">
                  Continue to animate
                </button>
                @if (projectHasPalette) {
                  <button
                    class="btn"
                    type="button"
                    (click)="applyPalette()"
                    [disabled]="busy || paletteBusy"
                    title="Snap pixels to the project palette"
                  >
                    {{ paletteBusy ? 'Applying…' : 'Apply palette' }}
                  </button>
                }
                <button class="btn" type="button" (click)="submit()" [disabled]="busy || !canSubmit">
                  {{ busy ? status : 'Try again' }}
                </button>
              </div>
            </div>
          } @else {
            <div class="panel empty">
              <p>{{ emptyHint }}</p>
            </div>
          }
        </aside>
      </div>
    </section>
  `,
  styles: [
    `
      .page {
        padding: 2.5rem 0 4rem;
        max-width: 72rem;
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
      .lead {
        color: var(--muted);
        max-width: 42rem;
      }
      .lead strong {
        color: var(--ink);
        font-weight: 600;
      }
      .tabs {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
        margin-top: 1.25rem;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        padding-bottom: 0.35rem;
      }
      .tab {
        border: 1px solid transparent;
        background: transparent;
        color: var(--muted);
        font: inherit;
        padding: 0.55rem 0.9rem;
        cursor: pointer;
        border-radius: 0;
      }
      .tab:hover {
        color: var(--ink);
      }
      .tab.active {
        color: var(--ink);
        border-color: rgba(255, 196, 120, 0.35);
        background: rgba(255, 196, 120, 0.1);
      }
      .layout {
        display: grid;
        grid-template-columns: minmax(0, 22rem) minmax(0, 1fr);
        gap: 2rem;
        margin-top: 1.25rem;
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
      }
      label {
        display: grid;
        gap: 0.4rem;
        font-size: 0.9rem;
      }
      .optional {
        color: var(--muted);
        font-size: 0.8rem;
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
      input[type='range'] {
        padding: 0.35rem 0;
      }
      .row {
        display: flex;
        align-items: center;
        gap: 0.75rem;
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
      .block {
        display: grid;
        gap: 0.5rem;
      }
      .block-label {
        font-size: 0.9rem;
      }
      .hint {
        color: var(--muted);
        font-size: 0.85rem;
      }
      .error {
        color: #ff8f8f;
      }
      .preview {
        min-height: 20rem;
        position: sticky;
        top: 1.5rem;
      }
      .panel {
        background: rgba(0, 0, 0, 0.22);
        border: 1px solid rgba(255, 255, 255, 0.08);
        padding: 1.25rem;
        display: grid;
        gap: 1rem;
      }
      .panel.empty {
        min-height: 22rem;
        place-items: center;
        color: var(--muted);
        text-align: center;
      }
      .panel img {
        width: min(100%, 28rem);
        image-rendering: pixelated;
        background:
          linear-gradient(45deg, #2a2a32 25%, transparent 25%),
          linear-gradient(-45deg, #2a2a32 25%, transparent 25%),
          linear-gradient(45deg, transparent 75%, #2a2a32 75%),
          linear-gradient(-45deg, transparent 75%, #2a2a32 75%);
        background-size: 16px 16px;
        background-position: 0 0, 0 8px, 8px -8px, -8px 0;
        background-color: #1a1a20;
        justify-self: center;
      }
      .meta {
        display: flex;
        flex-direction: column;
        gap: 0.2rem;
      }
      .meta span {
        color: var(--muted);
        font-size: 0.85rem;
      }
      .used-prompt {
        color: var(--muted);
        font-size: 0.8rem;
        margin: 0;
        line-height: 1.4;
      }
      .actions {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
      }
    `,
  ],
})
export class GeneratePage implements OnInit, AfterViewInit {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly ctx = inject(ProjectContextService);
  private readonly cdr = inject(ChangeDetectorRef);

  @ViewChild('picker') picker?: SpriteImagePickerComponent;

  assetKind: AssetKind = 'creature';
  mode: CreateMode = 'text2img';
  name = '';
  prompt = '';
  polishedPrompt = '';
  showPolished = false;
  polishSource: 'ollama' | 'fallback' | '' = '';
  style = 'pixel_art';
  styles: ArtStyle[] = [];
  pixelSize: 16 | 32 | 48 | 64 | 128 | 256 | 512 | 768 | 1024 = 128;
  dropShadow = false;
  outline = false;
  keyBackground = true;
  autoCrop = true;
  denoise = 0.72;
  croppedBlob: Blob | null = null;
  busy = false;
  polishing = false;
  paletteBusy = false;
  status = '';
  error = '';
  result: Character | Item | null = null;
  previewUrl = '';
  projectLabel = '';
  fromSourceId: string | null = null;
  private pendingReferenceUrl: string | null = null;

  get isItem(): boolean {
    return this.assetKind === 'item';
  }

  get projectHasPalette(): boolean {
    return (this.ctx.activeProject?.palette?.length || 0) > 0;
  }

  get pageTitle(): string {
    if (this.fromSourceId) {
      return this.isItem ? 'Recreate item' : 'Recreate creature';
    }
    return this.isItem ? 'New item' : 'New creature';
  }

  get modeBlurb(): string {
    if (this.mode === 'img2img') {
      return 'Upload a reference, crop it, then restyle with AI into your sprite format.';
    }
    if (this.mode === 'upload') {
      return 'Upload an existing image, crop it, and fit it to the selected export size.';
    }
    return this.selectedBlurb + ' Green-screen cutout (avoids pink fringes on white/fire).';
  }

  get selectedBlurb(): string {
    const s = this.styles.find((x) => x.id === this.style);
    if (s?.blurb) {
      return this.isItem ? s.blurb.replace(/creature/gi, 'item') : s.blurb;
    }
    return this.isItem ? 'Flux Dev item generation.' : 'Flux Dev creature generation.';
  }

  get sizeLabel(): string {
    const s = this.styles.find((x) => x.id === this.style);
    return s?.resize === 'nearest' ? 'Pixel size' : 'Export size';
  }

  get promptPlaceholder(): string {
    if (this.isItem) {
      if (this.mode === 'img2img') {
        return 'crystal potion bottle, cork stopper, glowing blue liquid — keep shape from reference';
      }
      return 'crystal potion bottle, cork stopper, glowing blue liquid, gold trim, clear silhouette';
    }
    if (this.mode === 'img2img') {
      return 'white horse, side view, blazing fire mane — keep pose from reference';
    }
    return 'white horse, side view, blazing orange-yellow fire mane and tail, ember sparks, clear legs';
  }

  get denoiseLabel(): string {
    if (this.denoise < 0.5) {
      return `${this.denoise.toFixed(2)} — keep close to reference`;
    }
    if (this.denoise > 0.8) {
      return `${this.denoise.toFixed(2)} — stronger restyle`;
    }
    return `${this.denoise.toFixed(2)} — balanced`;
  }

  get effectivePrompt(): string {
    const polished = this.polishedPrompt.trim();
    if (this.showPolished && polished) {
      return polished;
    }
    return this.prompt.trim();
  }

  get canSubmit(): boolean {
    if (this.mode === 'text2img') {
      return !!this.effectivePrompt;
    }
    if (this.mode === 'img2img') {
      return !!this.effectivePrompt && !!this.croppedBlob;
    }
    return !!this.croppedBlob;
  }

  get submitLabel(): string {
    if (this.busy) {
      return this.status || 'Working…';
    }
    if (this.result) {
      return this.mode === 'upload' ? 'Process again' : 'Regenerate';
    }
    if (this.mode === 'upload') {
      return 'Use image';
    }
    if (this.mode === 'img2img') {
      return 'Generate from image';
    }
    return 'Generate';
  }

  get emptyHint(): string {
    if (this.mode === 'upload') {
      return 'Preview appears here after processing. Crop tightly around the sprite.';
    }
    if (this.mode === 'img2img') {
      return 'Preview appears after img2img. Tweak strength or prompt until it looks right.';
    }
    return 'Preview appears here after generate. Tweak the prompt and regenerate until it looks right.';
  }

  ngOnInit(): void {
    const kind = this.route.snapshot.data['assetKind'];
    this.assetKind = kind === 'item' ? 'item' : 'creature';
    this.fromSourceId = this.route.snapshot.queryParamMap.get('from');
    void this.bootstrap();
  }

  ngAfterViewInit(): void {
    void this.flushPendingReference();
  }

  private async bootstrap(): Promise<void> {
    await this.ctx.refresh();
    if (!this.fromSourceId) {
      this.applyProjectDefaults();
    }
    try {
      const res = await firstValueFrom(this.api.styles());
      this.styles = res.styles || [];
    } catch {
      this.styles = [
        { id: 'pixel_art', label: 'Pixel art', blurb: 'Modern pixel LoRA + hard pixels', resize: 'nearest' },
        { id: 'cartoon', label: 'Cartoon', blurb: 'Soft game-mascot cartoon', resize: 'lanczos' },
        { id: 'anime', label: 'Anime', blurb: 'Anime / illustration look', resize: 'lanczos' },
        { id: 'comic', label: 'Comic', blurb: 'Bold comic / inked look', resize: 'lanczos' },
        { id: 'low_poly', label: 'Low poly', blurb: 'Facetted 3D low-poly render', resize: 'lanczos' },
        {
          id: 'realistic',
          label: 'Realistic',
          blurb: this.isItem ? 'Photoreal item still' : 'Photoreal creature still',
          resize: 'lanczos',
        },
      ];
    }
    if (this.fromSourceId) {
      await this.applyFromSource(this.fromSourceId);
    } else {
      this.applyProjectDefaults();
    }
  }

  private applyProjectDefaults(): void {
    const p = this.ctx.activeProject;
    this.projectLabel = p?.name || '';
    if (!p) {
      return;
    }
    if (p.default_style) {
      this.style = p.default_style;
    }
    if (
      p.default_pixel_size === 16 ||
      p.default_pixel_size === 32 ||
      p.default_pixel_size === 48 ||
      p.default_pixel_size === 64 ||
      p.default_pixel_size === 128 ||
      p.default_pixel_size === 256 ||
        p.default_pixel_size === 512 ||
        p.default_pixel_size === 768 ||
        p.default_pixel_size === 1024
    ) {
      this.pixelSize = p.default_pixel_size;
    }
    this.dropShadow = !!p.default_drop_shadow;
    this.outline = this.style === 'pixel_art' && !!p.default_outline;
  }

  private async applyFromSource(id: string): Promise<void> {
    try {
      const entity = this.isItem
        ? await firstValueFrom(this.api.getItem(id))
        : await firstValueFrom(this.api.getCharacter(id));
      if (entity.project_id) {
        this.ctx.setActiveProjectId(entity.project_id);
      }
      this.projectLabel = this.ctx.activeProject?.name || this.projectLabel;
      this.name = entity.name || '';
      this.prompt = (entity.prompt || '').trim();
      this.showPolished = false;
      this.polishedPrompt = '';
      this.polishSource = '';
      if (entity.style) {
        this.style = entity.style;
      }
      if (
        entity.pixel_size === 16 ||
        entity.pixel_size === 32 ||
        entity.pixel_size === 48 ||
        entity.pixel_size === 64 ||
        entity.pixel_size === 128 ||
        entity.pixel_size === 256 ||
        entity.pixel_size === 512 ||
        entity.pixel_size === 768 ||
        entity.pixel_size === 1024
      ) {
        this.pixelSize = entity.pixel_size;
      }
      this.dropShadow = !!entity.drop_shadow;
      this.outline = this.style === 'pixel_art' && !!entity.outline;
      this.mode = 'img2img';
      this.keyBackground = true;
      this.pendingReferenceUrl = this.api.fileUrl(entity.base_url || entity.preview_url || '');
      await this.flushPendingReference();
    } catch (e) {
      this.error = formatApiError(e, 'Could not load source for recreate');
      this.fromSourceId = null;
      this.applyProjectDefaults();
    }
  }

  private async flushPendingReference(): Promise<void> {
    const url = this.pendingReferenceUrl;
    if (!url) {
      return;
    }
    // Picker is only in the DOM for img2img/upload — force CD so ViewChild exists.
    this.cdr.detectChanges();
    if (!this.picker) {
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
      this.cdr.detectChanges();
    }
    if (!this.picker) {
      return;
    }
    this.pendingReferenceUrl = null;
    const fileName = `${(this.name || 'reference').replace(/\s+/g, '_')}.png`;
    await this.picker.loadFromUrl(url, fileName);
  }

  setMode(mode: CreateMode): void {
    if (this.mode === mode) {
      return;
    }
    this.mode = mode;
    this.error = '';
    this.result = null;
    this.previewUrl = '';
    if (mode === 'text2img') {
      this.croppedBlob = null;
      this.picker?.clear();
    }
  }

  onCropped(blob: Blob | null): void {
    this.croppedBlob = blob;
  }

  onStyleChange(): void {
    this.showPolished = false;
    this.polishedPrompt = '';
    this.polishSource = '';
    if (this.style !== 'pixel_art') {
      this.outline = false;
    }
  }

  async polish(): Promise<void> {
    this.polishing = true;
    this.error = '';
    this.polishSource = '';
    try {
      const res = await firstValueFrom(
        this.api.polishPrompt(
          this.prompt.trim(),
          this.style,
          this.outline,
          this.ctx.activeProjectId,
          this.isItem ? 'item' : 'character'
        )
      );
      this.polishedPrompt = res.prompt;
      this.polishSource = res.source;
      this.showPolished = true;
    } catch (e) {
      this.error = formatApiError(e);
    } finally {
      this.polishing = false;
    }
  }

  async submit(): Promise<void> {
    if (!this.canSubmit) {
      return;
    }
    if (!this.ctx.activeProjectId) {
      this.error = 'Select or create a project first.';
      return;
    }
    this.busy = true;
    this.error = '';
    this.status = 'queueing…';
    try {
      let jobId: string;
      let entityId: string | undefined;
      const defaultName = this.isItem ? 'Item' : 'Creature';
      if (this.mode === 'text2img') {
        if (this.isItem) {
          const res = await firstValueFrom(
            this.api.createItem({
              prompt: this.effectivePrompt,
              name: this.name.trim() || defaultName,
              project_id: this.ctx.activeProjectId,
              pixel_size: this.pixelSize,
              style: this.style,
              drop_shadow: this.dropShadow,
              outline: this.style === 'pixel_art' && this.outline,
              polish_prompt: false,
            })
          );
          jobId = res.job_id;
          entityId = res.item_id;
        } else {
          const res = await firstValueFrom(
            this.api.createCharacter({
              prompt: this.effectivePrompt,
              name: this.name.trim() || defaultName,
              project_id: this.ctx.activeProjectId,
              pixel_size: this.pixelSize,
              style: this.style,
              drop_shadow: this.dropShadow,
              outline: this.style === 'pixel_art' && this.outline,
              polish_prompt: false,
            })
          );
          jobId = res.job_id;
          entityId = res.character_id;
        }
      } else {
        if (!this.croppedBlob) {
          throw new Error('Crop an image first');
        }
        const fromImage = {
          file: this.croppedBlob,
          filename: 'crop.png',
          mode: (this.mode === 'img2img' ? 'img2img' : 'upload') as 'upload' | 'img2img',
          name: this.name.trim() || defaultName,
          project_id: this.ctx.activeProjectId,
          pixel_size: this.pixelSize,
          style: this.style,
          drop_shadow: this.dropShadow,
          outline: this.style === 'pixel_art' && this.outline,
          prompt: this.mode === 'img2img' ? this.effectivePrompt : this.prompt.trim(),
          key_background: this.keyBackground,
          auto_crop: this.mode === 'upload' ? this.autoCrop : true,
          denoise: this.mode === 'img2img' ? Number(this.denoise) : null,
          polish_prompt: false,
        };
        if (this.isItem) {
          const res = await firstValueFrom(this.api.createItemFromImage(fromImage));
          jobId = res.job_id;
          entityId = res.item_id;
        } else {
          const res = await firstValueFrom(this.api.createCharacterFromImage(fromImage));
          jobId = res.job_id;
          entityId = res.character_id;
        }
      }

      const job = await this.api.waitJob(jobId, (j) => {
        this.status = `${j.message} (${Math.round(j.progress * 100)}%)`;
      });
      if (job.status === 'failed') {
        throw new Error(job.error || 'Generation failed');
      }
      const eid = this.isItem
        ? ((job.result?.['item_id'] as string) || job.item_id || entityId)
        : ((job.result?.['character_id'] as string) || job.character_id || entityId);
      if (!eid) {
        throw new Error(this.isItem ? 'No item id returned' : 'No character id returned');
      }
      const entity = this.isItem
        ? await firstValueFrom(this.api.getItem(eid))
        : await firstValueFrom(this.api.getCharacter(eid));
      this.result = entity;
      const bust = Date.now();
      this.previewUrl = this.api.fileUrl(entity.preview_url || entity.base_url) + `?t=${bust}`;
    } catch (e) {
      this.error = formatApiError(e);
    } finally {
      this.busy = false;
      this.status = '';
    }
  }

  continueAnimate(): void {
    if (!this.result) {
      return;
    }
    void this.router.navigate([this.isItem ? '/items' : '/characters', this.result.id]);
  }

  async applyPalette(): Promise<void> {
    if (!this.result || !this.projectHasPalette) {
      return;
    }
    this.paletteBusy = true;
    this.error = '';
    try {
      if (this.isItem) {
        const res = await firstValueFrom(this.api.applyItemPalette(this.result.id, false));
        this.result = res.item;
      } else {
        const res = await firstValueFrom(this.api.applyCharacterPalette(this.result.id, false));
        this.result = res.character;
      }
      const bust = Date.now();
      this.previewUrl =
        this.api.fileUrl(this.result.preview_url || this.result.base_url) + `?t=${bust}`;
    } catch (e) {
      this.error = formatApiError(e, 'Could not apply palette');
    } finally {
      this.paletteBusy = false;
    }
  }
}
