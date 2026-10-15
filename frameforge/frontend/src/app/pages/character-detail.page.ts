import { Component, OnInit, inject } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { SpritePlayerComponent } from '../components/sprite-player.component';
import { LightboxDirective } from '../directives/lightbox.directive';
import {
  ApiService,
  ArtPurpose,
  ArtSize,
  ArtSizeOption,
  ArtStyle,
  ArtVersion,
  Character,
  SourceImage,
  StandingVersion,
  TrashedAnimation,
  TrashedArt,
  TrashedStanding,
  VariantMeta,
  formatApiError,
} from '../services/api.service';
import { LightboxItem } from '../services/lightbox.service';
import { ProjectContextService } from '../services/project-context.service';
import { animLabel, nextAnimName } from '../utils/anim-names';

@Component({
  selector: 'app-character-detail-page',
  standalone: true,
  imports: [FormsModule, RouterLink, SpritePlayerComponent, NgTemplateOutlet, LightboxDirective],
  template: `
    <ng-template #trashIcon>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path
          fill="currentColor"
          d="M9 3h6l1 2h4v2H4V5h4l1-2zm1 6h2v9h-2V9zm4 0h2v9h-2V9zM8 9h2v9H8V9zm-1 12h10a1 1 0 0 0 1-1V8H6v12a1 1 0 0 0 1 1z"
        />
      </svg>
    </ng-template>
    @if (!character && !error) {
      <p class="muted">Loading…</p>
    }
    @if (error) {
      <p class="error">{{ error }}</p>
    }
    @if (character) {
      <section class="page" [style.--sprite-display.px]="playbackSize">
        <a routerLink="/" class="back">← Gallery</a>
        <div class="top">
          <div>
            <h1>
              @if (character.ref) {
                <span class="ref">#{{ character.ref }}</span>
              }
              {{ character.name }}
            </h1>
            <p class="muted">{{ character.pixel_size }}px · id {{ character.id }}</p>
            <p class="prompt">{{ character.prompt }}</p>
            <div class="top-actions">
              <button type="button" class="btn" (click)="recreate()" [disabled]="busy">
                Recreate
              </button>
              @if (projectHasPalette) {
                <button
                  type="button"
                  class="btn"
                  (click)="applyPalette()"
                  [disabled]="busy || paletteBusy || standingBusy"
                  title="Snap base + animation frames to the project palette"
                >
                  {{ paletteBusy ? 'Applying…' : 'Apply palette' }}
                </button>
              }
            </div>
          </div>
          <img
            class="base"
            [src]="api.fileUrl(character.preview_url || character.base_url) + baseCacheQuery"
            [alt]="character.name"
            [appLightbox]="api.fileUrl(character.preview_url || character.base_url) + baseCacheQuery"
            [appLightboxAlt]="character.name"
            [appLightboxCaption]="character.name + ' · base'"
          />
        </div>

        <div class="source-step">
          <h2>Animation source</h2>
          <p class="muted">
            Default is the original character image. Optionally generate poses (standing, lying, …)
            and pick one as the source for new animations.
          </p>
          <div class="source-cards">
            <button
              type="button"
              class="source-card"
              [class.active]="activeSource === 'base'"
              (click)="chooseSource('base')"
              [disabled]="standingBusy"
            >
              <img
                [src]="api.fileUrl(character.preview_url || character.base_url)"
                alt="Original base"
                [appLightbox]="api.fileUrl(character.preview_url || character.base_url)"
                [appLightboxItems]="sourceLightboxItems"
                [appLightboxIndex]="0"
                appLightboxAlt="Original base"
                appLightboxCaption="Original"
              />
              <span class="source-title">Original</span>
              <span class="muted">Generated / uploaded character</span>
            </button>
            @for (v of standingVersions; track v.id) {
              <div
                class="source-card"
                [class.active]="isStandingActive(v.id)"
              >
                <button
                  type="button"
                  class="source-pick"
                  (click)="chooseSource('standing', v.id)"
                  [disabled]="standingBusy"
                >
                  @if (standingPreviewUrl(v); as preview) {
                    <img
                      [src]="api.fileUrl(preview) + standingCacheQuery"
                      [alt]="v.label || 'Pose'"
                      [appLightbox]="api.fileUrl(preview) + standingCacheQuery"
                      [appLightboxItems]="sourceLightboxItems"
                      [appLightboxIndex]="standingLightboxIndex(v.id)"
                      [appLightboxAlt]="v.label || 'Pose'"
                      [appLightboxCaption]="v.label || 'Pose'"
                    />
                  } @else {
                    <div class="source-placeholder">
                      <span class="muted">No preview</span>
                    </div>
                  }
                  <span class="source-title"
                    >@if (v.ref) {
                      <span class="ref">#{{ v.ref }}</span>
                    }
                    {{ v.label || 'Pose' }}</span
                  >
                  <span class="muted">{{ v.pose || 'Animation pose' }}</span>
                </button>
                <div class="source-actions">
                  <button
                    type="button"
                    class="icon-btn danger"
                    (click)="trashStanding(v.id)"
                    [disabled]="standingBusy || busy"
                    title="Trash"
                    aria-label="Trash"
                  >
                    <ng-container *ngTemplateOutlet="trashIcon" />
                  </button>
                </div>
              </div>
            }
            @if (!standingVersions.length) {
              <div class="source-card empty">
                <div class="source-placeholder">
                  <span class="source-title">Pose</span>
                  <span class="muted">Not generated yet</span>
                </div>
              </div>
            }
          </div>
          <div class="pose-build">
            <label class="pose-field">
              Pose
              <input
                [(ngModel)]="posePrompt"
                placeholder="standing"
                [disabled]="standingBusy || busy"
              />
            </label>
            <button
              type="button"
              class="btn"
              (click)="buildStanding()"
              [disabled]="standingBusy || busy || !posePrompt.trim()"
            >
              {{ standingBusy ? standingStatus : 'Generate pose' }}
            </button>
          </div>
          <p class="source-active muted">
            Active for new animations:
            <strong>{{ activeSourceLabel }}</strong>
          </p>
        </div>

        <div class="art-step">
          <h2>Art stills</h2>
          <p class="muted">
            Separate from animation sources — restyle for UI art. Pose may change; the creature just
            needs to stay clearly recognizable. Background is a real scene (optional description).
          </p>
          <div class="art-form">
            <label>
              Purpose
              <select [(ngModel)]="artPurpose" [disabled]="artBusy || busy">
                @for (p of artPurposes; track p.id) {
                  <option [value]="p.id">{{ p.label }}</option>
                }
              </select>
            </label>
            <label>
              Style
              <select [(ngModel)]="artStyle" [disabled]="artBusy || busy">
                @for (s of artStyles; track s.id) {
                  <option [value]="s.id">{{ s.label }}</option>
                }
              </select>
            </label>
            <label>
              Size
              <select [(ngModel)]="artSize" [disabled]="artBusy || busy">
                @for (s of artSizeOptions; track s.id) {
                  <option [ngValue]="s.id">{{ s.label }}</option>
                }
              </select>
            </label>
            <label class="grow">
              Background
              <input
                [(ngModel)]="artBackground"
                name="artBackground"
                placeholder="optional: misty volcanic ridge at dusk…"
                [disabled]="artBusy || busy"
              />
            </label>
            <label class="grow">
              Extra prompt
              <input
                [(ngModel)]="artExtraPrompt"
                name="artExtraPrompt"
                placeholder="optional mood, lighting, props…"
                [disabled]="artBusy || busy"
              />
            </label>
            <button
              type="button"
              class="btn primary"
              (click)="buildArt()"
              [disabled]="artBusy || busy || standingBusy"
            >
              {{ artBusy ? artStatus : 'Generate art' }}
            </button>
          </div>
          <div class="source-cards art-cards">
            @for (a of artVersions; track a.id) {
              <article class="source-card art-card">
                @if (artPreviewUrl(a); as preview) {
                  <img
                    [src]="api.fileUrl(preview) + artCacheQuery"
                    [alt]="a.label || 'Art'"
                    [appLightbox]="api.fileUrl(preview) + artCacheQuery"
                    [appLightboxItems]="artLightboxItems"
                    [appLightboxIndex]="artLightboxIndex(a.id)"
                    [appLightboxAlt]="a.label || 'Art'"
                    [appLightboxCaption]="
                      (a.label || 'Art') +
                      ' · ' +
                      (a.purpose || '') +
                      ' · ' +
                      (a.style || '') +
                      (a.size ? ' · ' + a.size + 'px' : '')
                    "
                  />
                } @else {
                  <div class="source-placeholder">
                    <span class="muted">No preview</span>
                  </div>
                }
                <span class="source-title"
                  >@if (a.ref) {
                    <span class="ref">#{{ a.ref }}</span>
                  }
                  {{ a.label || 'Art' }}</span
                >
                <span class="muted"
                  >{{ a.purpose || '' }} · {{ a.style || ''
                  }}{{ a.size ? ' · ' + a.size + 'px' : '' }}</span
                >
                <div class="source-actions">
                  <button
                    type="button"
                    class="icon-btn danger"
                    (click)="trashArt(a.id)"
                    [disabled]="artBusy || busy"
                    title="Trash"
                    aria-label="Trash"
                  >
                    <ng-container *ngTemplateOutlet="trashIcon" />
                  </button>
                </div>
              </article>
            } @empty {
              <p class="muted">No art stills yet.</p>
            }
          </div>
        </div>

        <div class="wizard">
          <h2>New animation</h2>
          <div class="row">
            <label>
              Type
              <select [(ngModel)]="animType">
                @for (p of presetKeys; track p) {
                  <option [value]="p">{{ p }}</option>
                }
                <option value="custom">custom…</option>
              </select>
            </label>
            @if (animType === 'custom') {
              <label>
                Custom
                <input [(ngModel)]="customType" placeholder="spin jump" />
              </label>
            }
            <label>
              Name
              <input
                [(ngModel)]="animName"
                [placeholder]="'auto → ' + suggestedAnimName"
              />
            </label>
            <label>
              Variants
              <input type="number" min="1" max="6" [(ngModel)]="variants" />
            </label>
            <label>
              Frames
              <input type="number" min="2" max="16" [(ngModel)]="frames" />
            </label>
            <label>
              FPS
              <input type="number" min="1" max="30" [(ngModel)]="fps" />
            </label>
            <label>
              Method
              <select [(ngModel)]="method">
                <option value="i2v">video → frames (Wan, best motion)</option>
                <option value="pose_keyframes">pose keyframes (Flux img2img from base)</option>
              </select>
            </label>
            <label class="motion-notes">
              Motion
              <textarea
                [(ngModel)]="motionNotes"
                rows="2"
                placeholder="e.g. very slow breathing bob, almost still · snappy frantic shake · heavy slow steps"
              ></textarea>
            </label>
          </div>
          <button class="btn primary" (click)="startAnimation()" [disabled]="busy || standingBusy">
            {{ busy ? jobStatus : 'Generate variants' }}
          </button>
        </div>

        <div class="anims">
          <h2>Animations</h2>
          @for (entry of animEntries; track entry.id) {
            <article class="anim">
              <header>
                <div class="anim-title">
                  @if (entry.ref) {
                    <span class="ref">#{{ entry.ref }}</span>
                  }
                  <input
                    class="anim-name-input"
                    [ngModel]="animNameDraft(entry)"
                    (ngModelChange)="setAnimNameDraft(entry.id, $event)"
                    (keydown.enter)="$any($event.target).blur()"
                    (blur)="commitAnimName(entry.id)"
                    [disabled]="busy || standingBusy"
                    [attr.aria-label]="'Rename ' + animLabel(entry)"
                  />
                  <span class="muted"
                    >{{ entry.type }} · {{ entry.fps || 8 }} fps · selected:
                    {{ entry.selected_variant === null ? 'none' : 'v' + entry.selected_variant }}</span
                  >
                </div>
                <button
                  type="button"
                  class="icon-btn danger"
                  (click)="trashAnimation(entry.id)"
                  [disabled]="busy || standingBusy"
                  title="Trash"
                  aria-label="Trash"
                >
                  <ng-container *ngTemplateOutlet="trashIcon" />
                </button>
              </header>
              <div class="variants">
                @for (v of entry.variants; track v.index) {
                  <div class="variant" [class.selected]="entry.selected_variant === v.index">
                    <div class="variant-layout">
                      <div class="playback">
                        <p class="col-label">Animation</p>
                        @if (v.video_url) {
                          <video
                            class="clip"
                            [src]="api.fileUrl(v.video_url)"
                            controls
                            loop
                            muted
                            playsinline
                            preload="metadata"
                          ></video>
                        }
                        <app-sprite-player
                          [frames]="variantFrames(entry.id, v)"
                          [fps]="entry.fps"
                          [size]="playbackSize"
                          [label]="animLabel(entry) + ' v' + v.index"
                          [playing]="false"
                          [persistSpeed]="true"
                          (fpsChange)="saveAnimFps(entry.id, $event)"
                        />
                      </div>
                      <div class="frames-panel">
                        <p class="col-label">Frames</p>
                        <div class="frame-strip">
                          @for (url of variantFrames(entry.id, v); track $index; let i = $index) {
                            <figure class="frame-cell" [class.active]="isFrameActive(entry.id, v.index, i)">
                              <button
                                type="button"
                                class="frame-btn"
                                (click)="selectFrame(entry.id, v.index, i, url)"
                                [title]="'Frame ' + (i + 1)"
                              >
                                <img [src]="url" [alt]="'frame ' + (i + 1)" />
                              </button>
                              <figcaption>{{ i + 1 }}</figcaption>
                            </figure>
                          } @empty {
                            <p class="muted">No frames</p>
                          }
                        </div>
                        @if (variantFrames(entry.id, v).length) {
                          <div class="frame-zoom">
                            <img
                              [src]="frameZoomUrl(entry.id, v)"
                              [alt]="'frame ' + (frameZoomIndex(entry.id, v) + 1)"
                              [appLightbox]="frameZoomUrl(entry.id, v)"
                              [appLightboxItems]="variantFrames(entry.id, v)"
                              [appLightboxIndex]="frameZoomIndex(entry.id, v)"
                              [appLightboxAlt]="'Frame ' + (frameZoomIndex(entry.id, v) + 1)"
                              [appLightboxCaption]="
                                animLabel(entry) +
                                ' v' +
                                v.index +
                                ' · frame ' +
                                (frameZoomIndex(entry.id, v) + 1)
                              "
                            />
                            <span class="muted"
                              >Frame {{ frameZoomIndex(entry.id, v) + 1 }} · click to enlarge</span
                            >
                          </div>
                        }
                      </div>
                    </div>
                    <div class="vmeta">
                      <span>v{{ v.index }} · {{ v.method }}{{ v.video_url ? ' · video' : '' }}</span>
                      <button
                        class="btn"
                        [class.active]="entry.selected_variant === v.index"
                        (click)="selectVariant(entry.id, v.index)"
                      >
                        {{ entry.selected_variant === v.index ? 'Selected' : 'Use this' }}
                      </button>
                    </div>
                  </div>
                }
              </div>
            </article>
          } @empty {
            <p class="muted">No animations yet.</p>
          }
        </div>

        <div class="export">
          <h2>Unity export</h2>
          <p class="muted">Exports selected animation variants as PNG sheet + JSON.</p>
          <button class="btn primary" (click)="exportUnity()" [disabled]="exporting">
            {{ exporting ? 'Exporting…' : 'Export spritesheet ZIP' }}
          </button>
          @if (exportUrl) {
            <a class="btn" [href]="exportUrl" download>Download ZIP</a>
          }
          @if (exportError) {
            <p class="error">{{ exportError }}</p>
          }
        </div>

        <div class="trash">
          <h2>Trash</h2>
          <p class="muted">Soft-deleted attempts for this creature. Restore anytime — nothing is wiped from disk.</p>
          @if (
            !trashAnimationEntries.length &&
            !trashStandingEntries.length &&
            !trashArtEntries.length
          ) {
            <p class="muted">No trashed animations, poses, or art stills.</p>
          }
          @if (trashAnimationEntries.length) {
            <h3>Animations</h3>
            <div class="trash-items">
              @for (entry of trashAnimationEntries; track entry.id) {
                <article class="trash-item anim" [class.open]="isTrashExpanded('anim:' + entry.id)">
                  <header>
                    <button
                      type="button"
                      class="trash-toggle"
                      (click)="toggleTrash('anim:' + entry.id)"
                    >
                      <span class="chevron">{{ isTrashExpanded('anim:' + entry.id) ? '▼' : '▶' }}</span>
                      @if (trashAnimThumb(entry); as thumb) {
                        <img
                          class="trash-thumb"
                          [src]="thumb"
                          alt=""
                          [appLightbox]="thumb"
                          appLightboxAlt="Trashed animation"
                          [appLightboxCaption]="animLabel(entry) + ' (trash)'"
                        />
                      }
                      <span class="anim-title">
                        <strong>{{ animLabel(entry) }}</strong>
                        <span class="muted"
                          >{{ entry.variants?.length || 0 }} variants ·
                          {{ formatTrashDate(entry.deleted_at) }}</span
                        >
                      </span>
                    </button>
                    <button type="button" class="btn" (click)="restoreAnimation(entry.id)">Restore</button>
                  </header>
                  @if (isTrashExpanded('anim:' + entry.id)) {
                    <div class="variants">
                      @for (v of entry.variants; track v.index) {
                        <div class="variant">
                          <div class="variant-layout">
                            <div class="playback">
                              <p class="col-label">Animation</p>
                              @if (v.video_url) {
                                <video
                                  class="clip"
                                  [src]="api.fileUrl(v.video_url)"
                                  controls
                                  loop
                                  muted
                                  playsinline
                                  preload="metadata"
                                ></video>
                              }
                              <app-sprite-player
                                [frames]="variantFrames(entry.id, v)"
                                [fps]="entry.fps"
                                [size]="playbackSize"
                                [label]="'trash ' + animLabel(entry) + ' v' + v.index"
                                [playing]="false"
                              />
                            </div>
                            <div class="frames-panel">
                              <p class="col-label">Frames</p>
                              <div class="frame-strip">
                                @for (url of variantFrames(entry.id, v); track $index; let i = $index) {
                                  <figure
                                    class="frame-cell"
                                    [class.active]="isFrameActive(entry.id, v.index, i)"
                                  >
                                    <button
                                      type="button"
                                      class="frame-btn"
                                      (click)="selectFrame(entry.id, v.index, i, url)"
                                      [title]="'Frame ' + (i + 1)"
                                    >
                                      <img [src]="url" [alt]="'frame ' + (i + 1)" />
                                    </button>
                                    <figcaption>{{ i + 1 }}</figcaption>
                                  </figure>
                                } @empty {
                                  <p class="muted">No frames</p>
                                }
                              </div>
                              @if (variantFrames(entry.id, v).length) {
                                <div class="frame-zoom">
                                  <img
                                    [src]="frameZoomUrl(entry.id, v)"
                                    [alt]="'frame ' + (frameZoomIndex(entry.id, v) + 1)"
                                    [appLightbox]="frameZoomUrl(entry.id, v)"
                                    [appLightboxItems]="variantFrames(entry.id, v)"
                                    [appLightboxIndex]="frameZoomIndex(entry.id, v)"
                                    [appLightboxAlt]="'Frame ' + (frameZoomIndex(entry.id, v) + 1)"
                                    [appLightboxCaption]="
                                      animLabel(entry) +
                                      ' v' +
                                      v.index +
                                      ' · frame ' +
                                      (frameZoomIndex(entry.id, v) + 1)
                                    "
                                  />
                                  <span class="muted"
                                    >Frame {{ frameZoomIndex(entry.id, v) + 1 }} · click to enlarge</span
                                  >
                                </div>
                              }
                            </div>
                          </div>
                          <div class="vmeta">
                            <span>v{{ v.index }} · {{ v.method }}{{ v.video_url ? ' · video' : '' }}</span>
                          </div>
                        </div>
                      }
                    </div>
                  }
                </article>
              }
            </div>
          }
          @if (trashStandingEntries.length) {
            <h3>Poses</h3>
            <div class="trash-items">
              @for (entry of trashStandingEntries; track entry.id) {
                <article class="trash-item anim" [class.open]="isTrashExpanded('standing:' + entry.id)">
                  <header>
                    <button
                      type="button"
                      class="trash-toggle"
                      (click)="toggleTrash('standing:' + entry.id)"
                    >
                      <span class="chevron">{{ isTrashExpanded('standing:' + entry.id) ? '▼' : '▶' }}</span>
                      @if (entry.preview_url) {
                        <img
                          class="trash-thumb"
                          [src]="api.fileUrl(entry.preview_url)"
                          alt="pose thumb"
                          [appLightbox]="api.fileUrl(entry.preview_url)"
                          appLightboxAlt="Trashed pose"
                          appLightboxCaption="Pose (trash)"
                        />
                      }
                      <span class="anim-title">
                        <strong>Pose</strong>
                        <span class="muted"
                          >{{ entry.id }} · {{ formatTrashDate(entry.deleted_at) }}</span
                        >
                      </span>
                    </button>
                    <button type="button" class="btn" (click)="restoreStanding(entry.id)">Restore</button>
                  </header>
                  @if (isTrashExpanded('standing:' + entry.id) && entry.preview_url) {
                    <div class="trash-standing-preview">
                      <img
                        [src]="api.fileUrl(entry.preview_url)"
                        alt="trashed pose"
                        [appLightbox]="api.fileUrl(entry.preview_url)"
                        appLightboxAlt="Trashed pose"
                        appLightboxCaption="Pose (trash)"
                      />
                    </div>
                  }
                </article>
              }
            </div>
          }
          @if (trashArtEntries.length) {
            <h3>Art stills</h3>
            <div class="trash-items">
              @for (entry of trashArtEntries; track entry.id) {
                <article class="trash-item anim" [class.open]="isTrashExpanded('art:' + entry.id)">
                  <header>
                    <button
                      type="button"
                      class="trash-toggle"
                      (click)="toggleTrash('art:' + entry.id)"
                    >
                      <span class="chevron">{{ isTrashExpanded('art:' + entry.id) ? '▼' : '▶' }}</span>
                      @if (entry.preview_url) {
                        <img
                          class="trash-thumb"
                          [src]="api.fileUrl(entry.preview_url)"
                          alt="art thumb"
                          [appLightbox]="api.fileUrl(entry.preview_url)"
                          [appLightboxItems]="trashArtLightboxItems"
                          [appLightboxIndex]="trashArtLightboxIndex(entry.id)"
                          [appLightboxAlt]="entry.label || 'Art'"
                          [appLightboxCaption]="(entry.label || 'Art') + ' (trash)'"
                        />
                      }
                      <span class="anim-title">
                        <strong>{{ entry.label || 'Art' }}</strong>
                        <span class="muted"
                          >{{ entry.size ? entry.size + 'px · ' : ''
                          }}{{ formatTrashDate(entry.deleted_at) }}</span
                        >
                      </span>
                    </button>
                    <button type="button" class="btn" (click)="restoreArt(entry.id)">Restore</button>
                  </header>
                  @if (isTrashExpanded('art:' + entry.id) && entry.preview_url) {
                    <div class="trash-standing-preview">
                      <img
                        [src]="api.fileUrl(entry.preview_url)"
                        alt="trashed art"
                        [appLightbox]="api.fileUrl(entry.preview_url)"
                        [appLightboxItems]="trashArtLightboxItems"
                        [appLightboxIndex]="trashArtLightboxIndex(entry.id)"
                        [appLightboxAlt]="entry.label || 'Art'"
                        [appLightboxCaption]="(entry.label || 'Art') + ' (trash)'"
                      />
                    </div>
                  }
                </article>
              }
            </div>
          }
        </div>
      </section>
    }
  `,
  styles: [
    `
      .page {
        padding: 2rem 0 4rem;
      }
      .back {
        color: var(--muted);
        text-decoration: none;
      }
      .top {
        display: grid;
        grid-template-columns: 1fr 220px;
        gap: 1.5rem;
        margin-top: 1rem;
        align-items: start;
      }
      @media (max-width: 720px) {
        .top {
          grid-template-columns: 1fr;
        }
      }
      h1,
      h2,
      h3 {
        font-family: var(--font-display);
        margin: 0;
      }
      h1 {
        font-size: 2.4rem;
      }
      h1 .ref {
        color: rgba(255, 196, 120, 0.95);
        margin-right: 0.4rem;
        font-size: 0.85em;
      }
      h2 {
        font-size: 1.6rem;
        margin-bottom: 0.8rem;
      }
      .prompt {
        color: var(--muted);
        max-width: 40rem;
      }
      .top-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 0.55rem;
        margin-top: 0.85rem;
      }
      .base {
        width: var(--sprite-display, 128px);
        height: var(--sprite-display, 128px);
        object-fit: contain;
        image-rendering: pixelated;
        background: #15181d;
        border: 1px solid rgba(255, 255, 255, 0.08);
      }
      .wizard,
      .source-step,
      .art-step,
      .anims,
      .export,
      .trash {
        margin-top: 2.5rem;
      }
      .source-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
      }
      .pose-build,
      .art-form {
        display: flex;
        flex-wrap: wrap;
        align-items: flex-end;
        gap: 0.75rem;
        margin-top: 0.85rem;
      }
      .pose-field,
      .art-form label {
        display: flex;
        flex-direction: column;
        gap: 0.35rem;
        font-size: 0.85rem;
        color: var(--muted);
      }
      .pose-field input,
      .art-form input,
      .art-form select {
        min-width: 12rem;
        padding: 0.45rem 0.6rem;
        border: 1px solid rgba(255, 255, 255, 0.12);
        background: #15181d;
        color: var(--ink);
        font: inherit;
      }
      .art-form label.grow {
        flex: 1 1 16rem;
      }
      .art-form label.grow input {
        width: 100%;
        min-width: 0;
      }
      .art-step {
        margin-top: 2.5rem;
      }
      .art-step > .muted {
        max-width: 42rem;
        margin: 0 0 1rem;
      }
      .art-cards {
        margin-top: 1rem;
      }
      .art-card {
        cursor: default;
      }
      .btn.danger {
        border-color: rgba(255, 120, 120, 0.35);
        color: #ffb0b0;
      }
      .icon-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 2rem;
        height: 2rem;
        padding: 0;
        border: 1px solid rgba(255, 255, 255, 0.12);
        background: rgba(0, 0, 0, 0.28);
        color: var(--muted);
        cursor: pointer;
      }
      .icon-btn svg {
        width: 1.05rem;
        height: 1.05rem;
        display: block;
      }
      .icon-btn.danger {
        border-color: rgba(255, 120, 120, 0.35);
        color: #ffb0b0;
      }
      .icon-btn:hover:not(:disabled) {
        color: #ffd0d0;
        border-color: rgba(255, 150, 150, 0.55);
      }
      .icon-btn:disabled {
        opacity: 0.45;
        cursor: default;
      }
      .anim-title {
        display: flex;
        flex-wrap: wrap;
        align-items: baseline;
        gap: 0.6rem;
      }
      .ref {
        color: rgba(255, 196, 120, 0.95);
        font-weight: 600;
        font-variant-numeric: tabular-nums;
      }
      .anim-name-input {
        font: inherit;
        font-size: 1.15rem;
        font-weight: 650;
        color: var(--ink);
        background: transparent;
        border: 1px solid transparent;
        border-radius: 4px;
        padding: 0.15rem 0.35rem;
        margin: -0.15rem -0.35rem;
        min-width: 6rem;
        max-width: 16rem;
      }
      .anim-name-input:hover:not(:disabled),
      .anim-name-input:focus {
        border-color: rgba(255, 255, 255, 0.18);
        background: rgba(0, 0, 0, 0.22);
        outline: none;
      }
      .trash > .muted {
        max-width: 40rem;
        margin: 0 0 1rem;
      }
      .trash h3 {
        margin: 1rem 0 0.55rem;
        font-size: 1rem;
      }
      .trash-items {
        display: grid;
        gap: 0.75rem;
      }
      .trash-item header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 0;
      }
      .trash-item.open header {
        margin-bottom: 0.85rem;
      }
      .trash-toggle {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        min-width: 0;
        padding: 0;
        border: 0;
        background: transparent;
        color: inherit;
        font: inherit;
        text-align: left;
        cursor: pointer;
      }
      .trash-toggle .chevron {
        color: var(--muted);
        font-size: 0.75rem;
        width: 1rem;
        flex: 0 0 auto;
      }
      .trash-thumb {
        width: 48px;
        height: 48px;
        object-fit: contain;
        image-rendering: pixelated;
        background: #15181d;
        border: 1px solid rgba(255, 255, 255, 0.08);
        flex: 0 0 auto;
      }
      .trash-standing-preview {
        display: flex;
        justify-content: flex-start;
      }
      .trash-standing-preview img {
        width: var(--sprite-display, 128px);
        height: var(--sprite-display, 128px);
        max-width: 100%;
        aspect-ratio: 1;
        object-fit: contain;
        image-rendering: pixelated;
        background: #15181d;
        border: 1px solid rgba(255, 255, 255, 0.08);
      }
      .source-step > .muted {
        max-width: 40rem;
        margin: 0 0 1rem;
      }
      .source-cards {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 220px));
        gap: 1rem;
        align-items: stretch;
      }
      .source-step .source-cards {
        grid-template-columns: repeat(
          auto-fit,
          minmax(max(7.5rem, calc(var(--sprite-display, 128px) + 2.5rem)), max-content)
        );
      }
      .source-card {
        display: flex;
        flex-direction: column;
        gap: 0.55rem;
        padding: 0.85rem;
        text-align: left;
        background: rgba(0, 0, 0, 0.18);
        border: 1px solid rgba(255, 255, 255, 0.08);
        color: inherit;
        font: inherit;
        cursor: pointer;
      }
      button.source-card {
        cursor: pointer;
      }
      .source-card.active {
        border-color: rgba(255, 196, 120, 0.65);
        background: rgba(255, 196, 120, 0.08);
      }
      .source-card.empty {
        cursor: default;
      }
      .source-card img {
        width: 100%;
        aspect-ratio: 1;
        object-fit: contain;
        image-rendering: pixelated;
        background: #15181d;
        border: 1px solid rgba(255, 255, 255, 0.06);
      }
      .source-step .source-card img {
        width: var(--sprite-display, 128px);
        height: var(--sprite-display, 128px);
        max-width: 100%;
        aspect-ratio: auto;
      }
      .source-pick {
        display: flex;
        flex-direction: column;
        gap: 0.55rem;
        padding: 0;
        border: 0;
        background: transparent;
        color: inherit;
        font: inherit;
        text-align: left;
        cursor: pointer;
      }
      .source-placeholder {
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 0.35rem;
        min-height: 180px;
        padding: 0.75rem;
        background: #15181d;
        border: 1px dashed rgba(255, 255, 255, 0.12);
      }
      .source-title {
        font-weight: 600;
      }
      .source-active {
        margin: 0.9rem 0 0;
      }
      .source-active strong {
        color: var(--ink);
        font-weight: 600;
      }
      .row {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 0.8rem;
        margin-bottom: 1rem;
      }
      label {
        display: grid;
        gap: 0.35rem;
        font-size: 0.85rem;
      }
      .motion-notes {
        grid-column: 1 / -1;
      }
      input,
      select,
      textarea {
        background: rgba(0, 0, 0, 0.28);
        border: 1px solid rgba(255, 255, 255, 0.1);
        color: var(--ink);
        padding: 0.55rem 0.65rem;
        font: inherit;
        resize: vertical;
      }
      .clip {
        display: block;
        width: var(--sprite-display, 128px);
        height: var(--sprite-display, 128px);
        object-fit: contain;
        background: #111;
        border: 1px solid rgba(255, 255, 255, 0.08);
      }
      .anim {
        margin-bottom: 1.5rem;
        padding: 1rem;
        background: rgba(0, 0, 0, 0.18);
        border: 1px solid rgba(255, 255, 255, 0.06);
      }
      .anim header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 0.8rem;
      }
      .variants {
        display: grid;
        gap: 1.25rem;
      }
      .variant {
        padding: 0.85rem;
        border: 1px solid transparent;
        overflow: hidden;
      }
      .variant.selected {
        border-color: rgba(255, 196, 120, 0.55);
        background: rgba(255, 196, 120, 0.08);
      }
      .variant-layout {
        display: grid;
        grid-template-columns: max-content minmax(0, 1fr);
        column-gap: 2.75rem;
        row-gap: 1rem;
        align-items: start;
      }
      @media (max-width: 900px) {
        .variant-layout {
          grid-template-columns: minmax(0, 1fr);
        }
      }
      .col-label {
        margin: 0 0 0.55rem;
        font-size: 0.8rem;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }
      .playback {
        grid-column: 1;
        display: flex;
        flex-direction: column;
        gap: 0.6rem;
        width: max-content;
        max-width: min(100%, max(var(--sprite-display, 128px), 12rem));
      }
      .playback app-sprite-player {
        display: block;
        max-width: 100%;
      }
      .frames-panel {
        grid-column: 2;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 0.85rem;
        border-left: 1px solid rgba(255, 255, 255, 0.08);
        padding-left: 1.75rem;
        margin-left: 0.25rem;
      }
      @media (max-width: 900px) {
        .playback,
        .frames-panel {
          grid-column: 1;
          max-width: none;
          width: auto;
        }
        .frames-panel {
          border-left: 0;
          border-top: 1px solid rgba(255, 255, 255, 0.08);
          padding-left: 0;
          margin-left: 0;
          padding-top: 1rem;
        }
      }
      .frame-strip {
        display: flex;
        flex-wrap: wrap;
        gap: 0.55rem;
        align-content: flex-start;
      }
      .frame-cell {
        margin: 0;
        width: var(--sprite-display, 128px);
        flex: 0 0 var(--sprite-display, 128px);
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
      }
      .frame-btn {
        display: block;
        width: var(--sprite-display, 128px);
        height: var(--sprite-display, 128px);
        padding: 0;
        border: 1px solid rgba(255, 255, 255, 0.1);
        background: #15181d;
        cursor: pointer;
      }
      .frame-cell.active .frame-btn {
        border-color: rgba(255, 196, 120, 0.75);
        box-shadow: inset 0 0 0 1px rgba(255, 196, 120, 0.35);
      }
      .frame-btn img {
        display: block;
        width: 100%;
        height: 100%;
        object-fit: contain;
        image-rendering: pixelated;
      }
      .frame-cell figcaption {
        text-align: center;
        font-size: 0.75rem;
        color: var(--muted);
        line-height: 1;
      }
      .frame-cell.active figcaption {
        color: var(--ink);
      }
      .frame-zoom {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: 0.35rem;
        margin-top: 0.25rem;
      }
      .frame-zoom img {
        width: var(--sprite-display, 128px);
        height: var(--sprite-display, 128px);
        object-fit: contain;
        image-rendering: pixelated;
        background: #15181d;
        border: 1px solid rgba(255, 255, 255, 0.1);
      }
      .vmeta {
        display: flex;
        justify-content: space-between;
        gap: 0.5rem;
        margin-top: 0.75rem;
        font-size: 0.8rem;
        color: var(--muted);
      }
      .vmeta .btn.active {
        border-color: rgba(255, 196, 120, 0.55);
        color: #ffd9a0;
      }
      .muted {
        color: var(--muted);
      }
      .error {
        color: #ff8f8f;
      }
      .export .btn {
        margin-right: 0.6rem;
      }
    `,
  ],
})
export class CharacterDetailPage implements OnInit {
  readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly ctx = inject(ProjectContextService);

  character: Character | null = null;
  error = '';
  presets: Record<string, string> = {};
  animType = 'walk_side';
  customType = '';
  animName = '';
  variants = 1;
  frames = 6;
  fps = 8;
  method: 'i2v' | 'pose_keyframes' = 'i2v';
  motionNotes = '';
  readonly animLabel = animLabel;
  private readonly animNameDrafts = new Map<string, string>();
  busy = false;
  paletteBusy = false;
  jobStatus = '';
  standingBusy = false;
  standingStatus = '';
  standingCacheBust = 0;
  baseCacheBust = 0;
  posePrompt = 'standing';
  artBusy = false;
  artStatus = '';
  artCacheBust = 0;
  artStyles: ArtStyle[] = [];
  artStyle = 'anime';
  artPurpose: ArtPurpose = 'portrait';
  artSize: ArtSize = 1024;
  artSizeOptions: ArtSizeOption[] = [
    { id: 512, label: '512 - inventory / thumb' },
    { id: 768, label: '768 - UI panel' },
    { id: 1024, label: '1024 - standard' },
    { id: 1280, label: '1280 - high-res still' },
  ];
  artBackground = '';
  artExtraPrompt = '';
  readonly artPurposes: { id: ArtPurpose; label: string }[] = [
    { id: 'portrait', label: 'Portrait' },
    { id: 'inventory', label: 'Inventory' },
    { id: 'showcase', label: 'Showcase' },
    { id: 'scene', label: 'Scene / background' },
  ];
  exporting = false;
  exportUrl = '';
  exportError = '';
  selectedFrameKey = '';
  selectedFrameIndex = 0;
  selectedFrameUrl = '';
  private readonly frameCache = new Map<string, string[]>();
  private readonly expandedTrash = new Set<string>();

  get presetKeys(): string[] {
    return Object.keys(this.presets);
  }

  get animEntries() {
    const anims = this.character?.animations || {};
    return Object.values(anims);
  }

  get suggestedAnimName(): string {
    const base = this.animType === 'custom' ? this.customType || 'custom' : this.animType;
    return nextAnimName(
      base,
      this.animEntries.map((e) => e.name || e.type)
    );
  }

  get trashAnimationEntries(): TrashedAnimation[] {
    const anims = this.character?.trash?.animations || {};
    return Object.values(anims).sort((a, b) =>
      String(b.deleted_at || '').localeCompare(String(a.deleted_at || ''))
    );
  }

  get trashStandingEntries(): TrashedStanding[] {
    return [...(this.character?.trash?.standing || [])];
  }

  get trashArtEntries(): TrashedArt[] {
    return [...(this.character?.trash?.art || [])];
  }

  get artVersions(): ArtVersion[] {
    return this.character?.art_versions || [];
  }

  toggleTrash(key: string): void {
    if (this.expandedTrash.has(key)) {
      this.expandedTrash.delete(key);
    } else {
      this.expandedTrash.add(key);
    }
  }

  isTrashExpanded(key: string): boolean {
    return this.expandedTrash.has(key);
  }

  trashAnimThumb(entry: TrashedAnimation): string {
    const v = entry.variants?.[0];
    if (!v) {
      return '';
    }
    return this.variantFrames(entry.id, v)[0] || '';
  }

  formatTrashDate(value?: string): string {
    if (!value) {
      return '';
    }
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) {
      return value;
    }
    return d.toLocaleString();
  }

  get standingVersions(): StandingVersion[] {
    return this.character?.standing_versions || [];
  }

  get activeSource(): SourceImage {
    const src = this.character?.source_image;
    if (src === 'standing' && this.character?.has_standing) {
      return 'standing';
    }
    return 'base';
  }

  get activeSourceLabel(): string {
    if (this.activeSource !== 'standing') {
      return 'Original';
    }
    const id = this.character?.active_standing_id;
    const v = this.standingVersions.find((x) => x.id === id);
    return v?.label || 'Standing';
  }

  get standingCacheQuery(): string {
    return this.standingCacheBust ? `?t=${this.standingCacheBust}` : '';
  }

  get artCacheQuery(): string {
    return this.artCacheBust ? `?t=${this.artCacheBust}` : '';
  }

  standingPreviewUrl(v: StandingVersion): string | null {
    return (
      v.preview_url ||
      v.files?.['standing_preview.png'] ||
      v.files?.['standing.png'] ||
      null
    );
  }

  artPreviewUrl(v: ArtVersion): string | null {
    return v.preview_url || v.files?.['art_preview.png'] || v.files?.['art.png'] || null;
  }

  get sourceLightboxItems(): LightboxItem[] {
    if (!this.character) {
      return [];
    }
    const items: LightboxItem[] = [
      {
        src: this.api.fileUrl(this.character.preview_url || this.character.base_url),
        alt: 'Original base',
        caption: 'Original',
      },
    ];
    for (const v of this.standingVersions) {
      const preview = this.standingPreviewUrl(v);
      if (!preview) {
        continue;
      }
      items.push({
        src: this.api.fileUrl(preview) + this.standingCacheQuery,
        alt: v.label || 'Pose',
        caption: v.label || 'Pose',
      });
    }
    return items;
  }

  standingLightboxIndex(standingId: string): number {
    const idx = this.standingVersions.findIndex((v) => v.id === standingId);
    return idx >= 0 ? idx + 1 : 0;
  }

  get artLightboxItems(): LightboxItem[] {
    const items: LightboxItem[] = [];
    for (const a of this.artVersions) {
      const preview = this.artPreviewUrl(a);
      if (!preview) {
        continue;
      }
      items.push({
        src: this.api.fileUrl(preview) + this.artCacheQuery,
        alt: a.label || 'Art',
        caption:
          (a.label || 'Art') +
          ' · ' +
          (a.purpose || '') +
          ' · ' +
          (a.style || '') +
          (a.size ? ' · ' + a.size + 'px' : ''),
      });
    }
    return items;
  }

  artLightboxIndex(artId: string): number {
    let i = 0;
    for (const a of this.artVersions) {
      if (!this.artPreviewUrl(a)) {
        continue;
      }
      if (a.id === artId) {
        return i;
      }
      i += 1;
    }
    return 0;
  }

  get trashArtLightboxItems(): LightboxItem[] {
    return this.trashArtEntries
      .filter((e) => !!e.preview_url)
      .map((e) => ({
        src: this.api.fileUrl(e.preview_url!) + this.artCacheQuery,
        alt: e.label || 'Art',
        caption: (e.label || 'Art') + ' (trash)',
      }));
  }

  trashArtLightboxIndex(artId: string): number {
    return Math.max(
      0,
      this.trashArtEntries.filter((e) => !!e.preview_url).findIndex((e) => e.id === artId)
    );
  }

  isStandingActive(standingId: string): boolean {
    return (
      this.activeSource === 'standing' &&
      this.character?.active_standing_id === standingId
    );
  }

  get playbackSize(): number {
    // 1:1 with authored pixel size — tiny sprites stay tiny on screen.
    const px = this.character?.pixel_size || 128;
    return Math.max(1, Math.min(512, px));
  }

  frameKey(animId: string, variantIndex: number, frameIndex: number): string {
    return `${animId}:${variantIndex}:${frameIndex}`;
  }

  variantFrames(animId: string, variant: VariantMeta): string[] {
    const key = `${animId}:${variant.index}`;
    let cached = this.frameCache.get(key);
    if (!cached) {
      cached = (variant.frame_urls || []).map((u) => this.api.fileUrl(u));
      this.frameCache.set(key, cached);
    }
    return cached;
  }

  selectFrame(animId: string, variantIndex: number, frameIndex: number, url: string): void {
    this.selectedFrameKey = this.frameKey(animId, variantIndex, frameIndex);
    this.selectedFrameIndex = frameIndex;
    this.selectedFrameUrl = url;
  }

  isFrameSelected(animId: string, variantIndex: number): boolean {
    return this.selectedFrameKey.startsWith(`${animId}:${variantIndex}:`);
  }

  isFrameActive(animId: string, variantIndex: number, frameIndex: number): boolean {
    if (this.isFrameSelected(animId, variantIndex)) {
      return this.selectedFrameKey === this.frameKey(animId, variantIndex, frameIndex);
    }
    return frameIndex === 0;
  }

  frameZoomIndex(animId: string, variant: VariantMeta): number {
    if (this.isFrameSelected(animId, variant.index)) {
      return this.selectedFrameIndex;
    }
    return 0;
  }

  frameZoomUrl(animId: string, variant: VariantMeta): string {
    const frames = this.variantFrames(animId, variant);
    const i = this.frameZoomIndex(animId, variant);
    return frames[i] || frames[0] || '';
  }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.api.presets().subscribe((p) => {
      this.presets = p.presets;
      this.animType = Object.keys(p.presets)[0] || 'walk_side';
    });
    this.api.styles().subscribe((p) => {
      this.artStyles = p.styles || [];
      if (!this.artStyles.some((s) => s.id === this.artStyle) && this.artStyles.length) {
        this.artStyle = this.artStyles[0].id;
      }
    });
    this.api.artSizes().subscribe({
      next: (p) => {
        if (p.sizes?.length) {
          this.artSizeOptions = p.sizes;
        }
        if (p.default) {
          this.artSize = p.default;
        }
      },
      error: () => {
        /* keep local defaults */
      },
    });
    this.reload(id);
  }

  reload(id: string): void {
    this.frameCache.clear();
    this.api.getCharacter(id).subscribe({
      next: (c) => {
        this.character = c;
        this.ensureDefaultFrameSelection();
      },
      error: (e) => (this.error = formatApiError(e, 'Failed to load')),
    });
  }

  get projectHasPalette(): boolean {
    const p =
      this.ctx.projects.find((x) => x.id === this.character?.project_id) ||
      this.ctx.activeProject;
    return (p?.palette?.length || 0) > 0;
  }

  get baseCacheQuery(): string {
    return this.baseCacheBust ? `?t=${this.baseCacheBust}` : '';
  }

  recreate(): void {
    if (!this.character) {
      return;
    }
    void this.router.navigate(['/generate'], {
      queryParams: { from: this.character.id },
    });
  }

  async applyPalette(): Promise<void> {
    if (!this.character || !this.projectHasPalette) {
      return;
    }
    this.paletteBusy = true;
    this.error = '';
    try {
      const res = await firstValueFrom(this.api.applyCharacterPalette(this.character.id, true));
      this.character = res.character;
      this.baseCacheBust = Date.now();
      this.standingCacheBust = Date.now();
      this.frameCache.clear();
    } catch (e) {
      this.error = formatApiError(e, 'Could not apply palette');
    } finally {
      this.paletteBusy = false;
    }
  }

  private ensureDefaultFrameSelection(): void {
    if (!this.character || this.selectedFrameKey) {
      return;
    }
    for (const entry of this.animEntries) {
      for (const v of entry.variants || []) {
        const frames = this.variantFrames(entry.id, v);
        if (frames.length) {
          this.selectFrame(entry.id, v.index, 0, frames[0]);
          return;
        }
      }
    }
  }

  async chooseSource(source: SourceImage, standingId?: string | null): Promise<void> {
    if (!this.character || this.standingBusy) {
      return;
    }
    if (source === 'standing') {
      if (!standingId || !this.standingVersions.some((v) => v.id === standingId)) {
        return;
      }
      if (this.isStandingActive(standingId)) {
        return;
      }
    } else if (this.activeSource === 'base') {
      return;
    }
    try {
      this.character = await firstValueFrom(
        this.api.setSourceImage(this.character.id, source, standingId)
      );
      this.standingCacheBust = Date.now();
    } catch (e) {
      this.error = formatApiError(e);
    }
  }

  async buildStanding(): Promise<void> {
    if (!this.character) {
      return;
    }
    const pose = this.posePrompt.trim() || 'standing';
    this.standingBusy = true;
    this.standingStatus = 'starting…';
    this.error = '';
    try {
      const res = await firstValueFrom(
        this.api.prepareStanding(this.character.id, true, pose)
      );
      const job = await this.api.waitJob(res.job_id, (j) => {
        this.standingStatus = `${j.message} (${Math.round(j.progress * 100)}%)`;
      });
      if (job.status === 'failed') {
        throw new Error(formatApiError(job.error, 'Pose generation failed'));
      }
      this.standingCacheBust = Date.now();
      this.reload(this.character.id);
    } catch (e) {
      this.error = formatApiError(e, 'Pose generation failed');
    } finally {
      this.standingBusy = false;
      this.standingStatus = '';
    }
  }

  async buildArt(): Promise<void> {
    if (!this.character) {
      return;
    }
    this.artBusy = true;
    this.artStatus = 'starting…';
    this.error = '';
    try {
      const res = await firstValueFrom(
        this.api.generateArt(this.character.id, {
          style: this.artStyle,
          purpose: this.artPurpose,
          size: this.artSize,
          background: this.artBackground.trim() || null,
          prompt: this.artExtraPrompt.trim() || null,
        })
      );
      const job = await this.api.waitJob(res.job_id, (j) => {
        this.artStatus = `${j.message} (${Math.round(j.progress * 100)}%)`;
      });
      if (job.status === 'failed') {
        throw new Error(formatApiError(job.error, 'Art generation failed'));
      }
      this.artCacheBust = Date.now();
      this.reload(this.character.id);
    } catch (e) {
      this.error = formatApiError(e, 'Art generation failed');
    } finally {
      this.artBusy = false;
      this.artStatus = '';
    }
  }

  async trashArt(artId: string): Promise<void> {
    if (!this.character) {
      return;
    }
    try {
      await firstValueFrom(this.api.deleteArt(this.character.id, artId));
      this.artCacheBust = Date.now();
      this.reload(this.character.id);
    } catch (e) {
      this.error = formatApiError(e, 'Could not move art to trash');
    }
  }

  async restoreArt(trashId: string): Promise<void> {
    if (!this.character) {
      return;
    }
    try {
      await firstValueFrom(this.api.restoreArt(this.character.id, trashId));
      this.artCacheBust = Date.now();
      this.reload(this.character.id);
    } catch (e) {
      this.error = formatApiError(e, 'Could not restore art');
    }
  }

  async startAnimation(): Promise<void> {
    if (!this.character) {
      return;
    }
    this.busy = true;
    this.jobStatus = 'starting…';
    const type = this.animType === 'custom' ? this.customType.trim() : this.animType;
    try {
      const res = await firstValueFrom(
        this.api.createAnimation(this.character.id, {
          anim_type: type,
          variants: this.variants,
          frames: this.frames,
          fps: this.fps,
          method: this.method,
          source_image: this.activeSource,
          motion_notes: this.motionNotes.trim(),
          name: this.animName.trim(),
        })
      );
      const job = await this.api.waitJob(res.job_id, (j) => {
        this.jobStatus = `${j.message} (${Math.round(j.progress * 100)}%)`;
      });
      if (job.status === 'failed') {
        throw new Error(formatApiError(job.error, 'Animation failed'));
      }
      this.animName = '';
      this.reload(this.character.id);
    } catch (e) {
      this.error = formatApiError(e, 'Animation failed');
    } finally {
      this.busy = false;
    }
  }

  animNameDraft(entry: { id: string; name?: string; type: string }): string {
    return this.animNameDrafts.get(entry.id) ?? animLabel(entry);
  }

  setAnimNameDraft(animationId: string, value: string): void {
    this.animNameDrafts.set(animationId, value);
  }

  async selectVariant(animationId: string, index: number): Promise<void> {
    if (!this.character) {
      return;
    }
    const current = this.character.animations?.[animationId]?.selected_variant;
    const next = current === index ? null : index;
    try {
      await firstValueFrom(this.api.selectVariant(this.character.id, animationId, next));
      this.reload(this.character.id);
    } catch (e) {
      this.error = formatApiError(e, 'Could not update variant selection');
    }
  }

  async commitAnimName(animationId: string): Promise<void> {
    if (!this.character) {
      return;
    }
    const current = this.character.animations?.[animationId];
    const prev = animLabel(current || { type: '' });
    const name = (this.animNameDrafts.get(animationId) ?? prev).trim();
    if (!name || name === prev) {
      this.animNameDrafts.delete(animationId);
      return;
    }
    try {
      await firstValueFrom(this.api.renameAnimation(this.character.id, animationId, name));
      this.animNameDrafts.delete(animationId);
      this.reload(this.character.id);
    } catch (e) {
      this.error = formatApiError(e, 'Could not rename animation');
      this.animNameDrafts.set(animationId, prev);
    }
  }

  async saveAnimFps(animationId: string, fps: number): Promise<void> {
    if (!this.character) {
      return;
    }
    const current = this.character.animations?.[animationId];
    if (!current || current.fps === fps) {
      return;
    }
    try {
      const updated = await firstValueFrom(
        this.api.updateAnimation(this.character.id, animationId, { fps })
      );
      if (this.character.animations?.[animationId]) {
        this.character.animations[animationId] = {
          ...this.character.animations[animationId],
          fps: updated.fps,
        };
      }
    } catch (e) {
      this.error = formatApiError(e, 'Could not save animation speed');
    }
  }

  async trashAnimation(animationId: string): Promise<void> {
    if (!this.character) {
      return;
    }
    try {
      await firstValueFrom(this.api.deleteAnimation(this.character.id, animationId));
      this.reload(this.character.id);
    } catch (e) {
      this.error = formatApiError(e, 'Could not move animation to trash');
    }
  }

  async restoreAnimation(animationId: string): Promise<void> {
    if (!this.character) {
      return;
    }
    try {
      await firstValueFrom(this.api.restoreAnimation(this.character.id, animationId));
      this.reload(this.character.id);
    } catch (e) {
      this.error = formatApiError(e, 'Could not restore animation');
    }
  }

  async trashStanding(standingId?: string | null): Promise<void> {
    if (!this.character) {
      return;
    }
    try {
      await firstValueFrom(this.api.deleteStanding(this.character.id, standingId));
      this.standingCacheBust = Date.now();
      this.reload(this.character.id);
    } catch (e) {
      this.error = formatApiError(e, 'Could not move standing to trash');
    }
  }

  async restoreStanding(trashId: string): Promise<void> {
    if (!this.character) {
      return;
    }
    try {
      await firstValueFrom(this.api.restoreStanding(this.character.id, trashId));
      this.standingCacheBust = Date.now();
      this.reload(this.character.id);
    } catch (e) {
      this.error = formatApiError(e, 'Could not restore standing');
    }
  }

  async exportUnity(): Promise<void> {
    if (!this.character) {
      return;
    }
    this.exporting = true;
    this.exportError = '';
    try {
      const res = await firstValueFrom(this.api.exportUnity(this.character.id));
      this.exportUrl = this.api.fileUrl(res.zip_url);
    } catch (e) {
      this.exportError = e instanceof Error ? e.message : String(e);
    } finally {
      this.exporting = false;
    }
  }
}
