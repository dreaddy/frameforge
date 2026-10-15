import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Subscription, firstValueFrom, forkJoin, of, timer } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';
import { LightboxDirective } from '../directives/lightbox.directive';
import {
  ApiService,
  Character,
  Health,
  Item,
  TrashedCharacter,
  TrashedItem,
  formatApiError,
} from '../services/api.service';
import { ProjectContextService } from '../services/project-context.service';

type AssetKind = 'creatures' | 'items' | 'backgrounds' | 'tilesets';

@Component({
  selector: 'app-gallery-page',
  standalone: true,
  imports: [RouterLink, LightboxDirective],
  template: `
    <section class="page-head">
      <div class="head-copy">
        <p class="eyebrow">Asset library</p>
        <h1>{{ projectName || 'Frameforge' }}</h1>
        <p class="lead">
          Game-ready sprites for Unity — creatures first, then items, backgrounds, and tilesets.
        </p>
      </div>
      <div class="head-side">
        <div class="status" aria-label="Service status">
          <span [class.ok]="health?.comfy?.ok"
            >Comfy {{ health?.comfy?.ok ? 'online' : 'offline' }}</span
          >
          <span [class.ok]="health?.ollama?.ok"
            >Ollama {{ health?.ollama?.ok ? 'online' : 'offline' }}</span
          >
        </div>
        <div class="cta">
          @if (assetKind === 'creatures') {
            <a routerLink="/generate" class="btn primary">New creature</a>
          } @else if (assetKind === 'items') {
            <a routerLink="/generate-item" class="btn primary">New item</a>
          }
          <a routerLink="/projects" class="btn">Manage projects</a>
        </div>
      </div>
    </section>

    <div class="asset-tabs" role="tablist" aria-label="Asset type">
      @for (tab of assetTabs; track tab.id) {
        <button
          type="button"
          role="tab"
          class="asset-tab"
          [class.active]="assetKind === tab.id"
          [class.soon]="tab.soon"
          [attr.aria-selected]="assetKind === tab.id"
          [disabled]="tab.soon"
          (click)="setAssetKind(tab.id)"
        >
          {{ tab.label }}
          @if (tab.soon) {
            <span class="soon-tag">soon</span>
          } @else if (tab.id === 'creatures') {
            <span class="count">{{ characters.length }}</span>
          } @else if (tab.id === 'items') {
            <span class="count">{{ items.length }}</span>
          }
        </button>
      }
    </div>

    @if (assetKind === 'creatures') {
      <section class="gallery">
        <div class="section-head">
          <h2>Creatures</h2>
          <p class="muted">Base sprites, poses, art stills, and animation loops.</p>
        </div>
        @if (error) {
          <p class="error">{{ error }}</p>
        }
        @if (loading) {
          <p class="muted">Loading…</p>
        } @else if (!characters.length) {
          <div class="empty">
            <p>No creatures in this project yet.</p>
            <a routerLink="/generate" class="btn primary">Create or upload one</a>
          </div>
        } @else {
          <div class="grid">
            @for (c of characters; track c.id) {
              <div class="tile">
                <a class="tile-link" [routerLink]="['/characters', c.id]">
                  <img
                    [src]="api.fileUrl(c.preview_url || c.base_url)"
                    [alt]="c.name"
                  />
                  <div>
                    <strong
                      >@if (c.ref) {
                        <span class="ref">#{{ c.ref }}</span>
                      }
                      {{ c.name }}</strong
                    >
                    <span
                      >{{ c.style || 'pixel_art' }} · {{ c.pixel_size }}px ·
                      {{ c.animation_ids?.length || 0 }} anims</span
                    >
                  </div>
                </a>
                <button
                  type="button"
                  class="btn trash-btn"
                  (click)="trashCharacter(c)"
                  [disabled]="busyId === c.id"
                >
                  {{ busyId === c.id ? '…' : 'Trash' }}
                </button>
              </div>
            }
          </div>
        }
      </section>

      <section class="trash">
        <button type="button" class="trash-toggle" (click)="trashOpen = !trashOpen">
          <span class="chevron">{{ trashOpen ? '▼' : '▶' }}</span>
          <h2>Trash</h2>
          <span class="muted count">{{ trashed.length }}</span>
        </button>
        @if (trashOpen) {
          <p class="muted">Soft-deleted creatures. Restore anytime — nothing is wiped.</p>
          @if (!trashed.length) {
            <p class="muted">Trash is empty.</p>
          } @else {
            <div class="trash-grid">
              @for (c of trashed; track c.id) {
                <article class="trash-tile">
                  <img
                    [src]="api.fileUrl(c.preview_url || c.base_url || '')"
                    [alt]="c.name"
                    [appLightbox]="api.fileUrl(c.preview_url || c.base_url || '')"
                    [appLightboxItems]="trashGalleryUrls"
                    [appLightboxIndex]="trashLightboxIndex(c.id)"
                    [appLightboxAlt]="c.name"
                    [appLightboxCaption]="c.name + ' (trash)'"
                  />
                  <div class="meta">
                    <strong
                      >@if (c.ref) {
                        <span class="ref">#{{ c.ref }}</span>
                      }
                      {{ c.name }}</strong
                    >
                    <span
                      >{{ c.style || 'pixel_art' }} · {{ c.pixel_size || '?' }}px ·
                      {{ formatDate(c.deleted_at) }}</span
                    >
                  </div>
                  <button
                    type="button"
                    class="btn"
                    (click)="restoreCharacter(c)"
                    [disabled]="busyId === c.id"
                  >
                    {{ busyId === c.id ? '…' : 'Restore' }}
                  </button>
                </article>
              }
            </div>
          }
        }
      </section>
    } @else if (assetKind === 'items') {
      <section class="gallery">
        <div class="section-head">
          <h2>Items</h2>
          <p class="muted">Props and collectibles — art stills, idle / destroyed / use loops.</p>
        </div>
        @if (error) {
          <p class="error">{{ error }}</p>
        }
        @if (loading) {
          <p class="muted">Loading…</p>
        } @else if (!items.length) {
          <div class="empty">
            <p>No items in this project yet.</p>
            <a routerLink="/generate-item" class="btn primary">Create or upload one</a>
          </div>
        } @else {
          <div class="grid">
            @for (it of items; track it.id) {
              <div class="tile">
                <a class="tile-link" [routerLink]="['/items', it.id]">
                  <img
                    [src]="api.fileUrl(it.preview_url || it.base_url)"
                    [alt]="it.name"
                  />
                  <div>
                    <strong
                      >@if (it.ref) {
                        <span class="ref">#{{ it.ref }}</span>
                      }
                      {{ it.name }}</strong
                    >
                    <span
                      >{{ it.style || 'pixel_art' }} · {{ it.pixel_size }}px ·
                      {{ it.animation_ids?.length || 0 }} anims</span
                    >
                  </div>
                </a>
                <button
                  type="button"
                  class="btn trash-btn"
                  (click)="trashItem(it)"
                  [disabled]="busyId === it.id"
                >
                  {{ busyId === it.id ? '…' : 'Trash' }}
                </button>
              </div>
            }
          </div>
        }
      </section>

      <section class="trash">
        <button type="button" class="trash-toggle" (click)="itemsTrashOpen = !itemsTrashOpen">
          <span class="chevron">{{ itemsTrashOpen ? '▼' : '▶' }}</span>
          <h2>Trash</h2>
          <span class="muted count">{{ trashedItems.length }}</span>
        </button>
        @if (itemsTrashOpen) {
          <p class="muted">Soft-deleted items. Restore anytime — nothing is wiped.</p>
          @if (!trashedItems.length) {
            <p class="muted">Trash is empty.</p>
          } @else {
            <div class="trash-grid">
              @for (it of trashedItems; track it.id) {
                <article class="trash-tile">
                  <img
                    [src]="api.fileUrl(it.preview_url || it.base_url || '')"
                    [alt]="it.name"
                    [appLightbox]="api.fileUrl(it.preview_url || it.base_url || '')"
                    [appLightboxItems]="itemTrashGalleryUrls"
                    [appLightboxIndex]="itemTrashLightboxIndex(it.id)"
                    [appLightboxAlt]="it.name"
                    [appLightboxCaption]="it.name + ' (trash)'"
                  />
                  <div class="meta">
                    <strong
                      >@if (it.ref) {
                        <span class="ref">#{{ it.ref }}</span>
                      }
                      {{ it.name }}</strong
                    >
                    <span
                      >{{ it.style || 'pixel_art' }} · {{ it.pixel_size || '?' }}px ·
                      {{ formatDate(it.deleted_at) }}</span
                    >
                  </div>
                  <button
                    type="button"
                    class="btn"
                    (click)="restoreItem(it)"
                    [disabled]="busyId === it.id"
                  >
                    {{ busyId === it.id ? '…' : 'Restore' }}
                  </button>
                </article>
              }
            </div>
          }
        }
      </section>
    } @else {
      <section class="coming-soon">
        <h2>{{ activeTabLabel }}</h2>
        <p class="muted">
          Planned for this project — same generate / upload / export flow as creatures, tuned for
          {{ activeTabLabel.toLowerCase() }}.
        </p>
      </section>
    }
  `,
  styles: [
    `
      .page-head {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: 1.25rem 2rem;
        align-items: end;
        padding: 1.75rem 0 1.25rem;
      }
      @media (max-width: 720px) {
        .page-head {
          grid-template-columns: 1fr;
        }
      }
      .eyebrow {
        margin: 0 0 0.35rem;
        color: var(--accent);
        font-size: 0.8rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
      }
      h1 {
        margin: 0;
        font-family: var(--font-display);
        font-size: clamp(1.9rem, 4vw, 2.6rem);
        letter-spacing: -0.03em;
        line-height: 1.1;
      }
      .lead {
        max-width: 34rem;
        color: var(--muted);
        margin: 0.55rem 0 0;
      }
      .head-side {
        display: grid;
        gap: 0.85rem;
        justify-items: end;
      }
      @media (max-width: 720px) {
        .head-side {
          justify-items: start;
        }
      }
      .cta {
        display: flex;
        flex-wrap: wrap;
        gap: 0.65rem;
      }
      .status {
        display: flex;
        gap: 0.85rem;
        font-size: 0.8rem;
        color: #9aa3ad;
      }
      .status .ok {
        color: #7dcea0;
      }
      .asset-tabs {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
        padding: 0.25rem 0 0.15rem;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      }
      .asset-tab {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        border: 1px solid transparent;
        background: transparent;
        color: var(--muted);
        font: inherit;
        font-weight: 500;
        padding: 0.6rem 0.9rem;
        cursor: pointer;
      }
      .asset-tab:hover:not(:disabled) {
        color: var(--ink);
      }
      .asset-tab.active {
        color: var(--ink);
        border-color: rgba(255, 196, 120, 0.4);
        background: rgba(255, 196, 120, 0.1);
      }
      .asset-tab.soon {
        opacity: 0.55;
        cursor: default;
      }
      .soon-tag,
      .count {
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: var(--muted);
      }
      .asset-tab.active .count {
        color: var(--accent);
      }
      .gallery,
      .trash,
      .coming-soon {
        padding: 1.5rem 0 2rem;
      }
      .trash {
        padding-bottom: 4rem;
        border-top: 1px solid rgba(255, 255, 255, 0.06);
      }
      .section-head {
        display: grid;
        gap: 0.25rem;
        margin-bottom: 0.75rem;
      }
      .section-head h2,
      .coming-soon h2,
      .trash-toggle h2 {
        font-family: var(--font-display);
        font-size: 1.55rem;
        margin: 0;
      }
      .section-head .muted,
      .coming-soon .muted {
        margin: 0;
      }
      .empty {
        display: grid;
        gap: 1rem;
        justify-items: start;
        padding: 2rem 0;
        color: var(--muted);
      }
      .empty p {
        margin: 0;
      }
      .coming-soon {
        min-height: 12rem;
      }
      .trash-toggle {
        display: flex;
        align-items: baseline;
        gap: 0.55rem;
        width: 100%;
        padding: 0;
        border: 0;
        background: transparent;
        color: inherit;
        font: inherit;
        cursor: pointer;
        text-align: left;
      }
      .trash-toggle .chevron {
        color: var(--muted);
        font-size: 0.85rem;
        width: 1rem;
      }
      .trash-toggle .count {
        font-size: 0.9rem;
        text-transform: none;
        letter-spacing: 0;
      }
      .trash > .muted {
        margin: 0.5rem 0 0;
      }
      .grid,
      .trash-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
        gap: 1rem;
        margin-top: 1rem;
      }
      .tile,
      .trash-tile {
        background: rgba(0, 0, 0, 0.22);
        border: 1px solid rgba(255, 255, 255, 0.06);
        padding: 0.75rem;
        display: grid;
        gap: 0.6rem;
        transition: transform 0.2s ease, border-color 0.2s ease;
      }
      .tile:hover,
      .trash-tile:hover {
        transform: translateY(-3px);
        border-color: rgba(255, 196, 120, 0.35);
      }
      .tile-link {
        text-decoration: none;
        color: inherit;
        display: grid;
        gap: 0.6rem;
      }
      .tile img,
      .trash-tile img {
        width: 100%;
        aspect-ratio: 1;
        object-fit: contain;
        image-rendering: pixelated;
        background: #15181d;
      }
      .ref {
        color: rgba(255, 196, 120, 0.95);
        font-weight: 600;
        margin-right: 0.35rem;
      }
      .tile strong,
      .trash-tile strong {
        display: block;
      }
      .tile span,
      .trash-tile span,
      .muted {
        color: var(--muted);
        font-size: 0.85rem;
      }
      .trash-btn {
        justify-self: start;
        color: #ff8f8f;
      }
      .error {
        color: #ff8f8f;
      }
      .meta {
        display: grid;
        gap: 0.2rem;
      }
    `,
  ],
})
export class GalleryPage implements OnInit, OnDestroy {
  readonly api = inject(ApiService);
  private readonly ctx = inject(ProjectContextService);
  characters: Character[] = [];
  trashed: TrashedCharacter[] = [];
  items: Item[] = [];
  trashedItems: TrashedItem[] = [];
  health: Health | null = null;
  loading = true;
  projectName = '';
  busyId: string | null = null;
  error = '';
  trashOpen = false;
  itemsTrashOpen = false;
  assetKind: AssetKind = 'creatures';
  readonly assetTabs: { id: AssetKind; label: string; soon?: boolean }[] = [
    { id: 'creatures', label: 'Creatures' },
    { id: 'items', label: 'Items' },
    { id: 'backgrounds', label: 'Backgrounds', soon: true },
    { id: 'tilesets', label: 'Tilesets', soon: true },
  ];
  private sub?: Subscription;

  get activeTabLabel(): string {
    return this.assetTabs.find((t) => t.id === this.assetKind)?.label || 'Assets';
  }

  ngOnInit(): void {
    this.sub = new Subscription();
    this.sub.add(
      timer(0, 15000)
        .pipe(switchMap(() => this.api.health().pipe(catchError(() => of(null)))))
        .subscribe((h) => {
          if (h) {
            this.health = h;
          }
        })
    );
    this.sub.add(
      this.ctx.activeProjectId$.subscribe((id) => {
        this.projectName = this.ctx.activeProject?.name || '';
        this.loadLists(id);
      })
    );
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  setAssetKind(kind: AssetKind): void {
    const tab = this.assetTabs.find((t) => t.id === kind);
    if (!tab || tab.soon) {
      return;
    }
    this.assetKind = kind;
  }

  get trashGalleryUrls(): string[] {
    return this.trashed
      .map((c) => this.api.fileUrl(c.preview_url || c.base_url || ''))
      .filter((url) => !!url);
  }

  get itemTrashGalleryUrls(): string[] {
    return this.trashedItems
      .map((c) => this.api.fileUrl(c.preview_url || c.base_url || ''))
      .filter((url) => !!url);
  }

  trashLightboxIndex(id: string): number {
    return Math.max(
      0,
      this.trashed.findIndex((c) => c.id === id)
    );
  }

  itemTrashLightboxIndex(id: string): number {
    return Math.max(
      0,
      this.trashedItems.findIndex((c) => c.id === id)
    );
  }

  formatDate(value?: string): string {
    if (!value) {
      return 'unknown date';
    }
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) {
      return value;
    }
    return d.toLocaleString();
  }

  async trashCharacter(c: Character): Promise<void> {
    if (!confirm(`Move “${c.name}” to trash?`)) {
      return;
    }
    this.busyId = c.id;
    this.error = '';
    try {
      await firstValueFrom(this.api.trashCharacter(c.id));
      await this.loadLists(this.ctx.activeProjectId);
    } catch (e) {
      this.error = formatApiError(e);
    } finally {
      this.busyId = null;
    }
  }

  async restoreCharacter(c: TrashedCharacter): Promise<void> {
    this.busyId = c.id;
    this.error = '';
    try {
      await firstValueFrom(this.api.restoreCharacter(c.id));
      await this.loadLists(this.ctx.activeProjectId);
    } catch (e) {
      this.error = formatApiError(e);
    } finally {
      this.busyId = null;
    }
  }

  async trashItem(it: Item): Promise<void> {
    if (!confirm(`Move “${it.name}” to trash?`)) {
      return;
    }
    this.busyId = it.id;
    this.error = '';
    try {
      await firstValueFrom(this.api.trashItem(it.id));
      await this.loadLists(this.ctx.activeProjectId);
    } catch (e) {
      this.error = formatApiError(e);
    } finally {
      this.busyId = null;
    }
  }

  async restoreItem(it: TrashedItem): Promise<void> {
    this.busyId = it.id;
    this.error = '';
    try {
      await firstValueFrom(this.api.restoreItem(it.id));
      await this.loadLists(this.ctx.activeProjectId);
    } catch (e) {
      this.error = formatApiError(e);
    } finally {
      this.busyId = null;
    }
  }

  private async loadLists(projectId: string | null): Promise<void> {
    this.loading = true;
    this.error = '';
    try {
      const result = await firstValueFrom(
        forkJoin({
          characters: this.api.listCharacters(projectId).pipe(catchError(() => of([] as Character[]))),
          trashed: this.api
            .listTrashedCharacters(projectId)
            .pipe(catchError(() => of([] as TrashedCharacter[]))),
          items: this.api.listItems(projectId).pipe(catchError(() => of([] as Item[]))),
          trashedItems: this.api
            .listTrashedItems(projectId)
            .pipe(catchError(() => of([] as TrashedItem[]))),
        })
      );
      this.characters = result.characters;
      this.trashed = result.trashed;
      this.items = result.items;
      this.trashedItems = result.trashedItems;
      this.projectName = this.ctx.activeProject?.name || '';
    } finally {
      this.loading = false;
    }
  }
}
