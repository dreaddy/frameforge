import {
  Component,
  EventEmitter,
  Input,
  NgZone,
  OnChanges,
  OnDestroy,
  Output,
  SimpleChanges,
  inject,
} from '@angular/core';
import { LightboxDirective } from '../directives/lightbox.directive';

@Component({
  selector: 'app-sprite-player',
  standalone: true,
  imports: [LightboxDirective],
  template: `
    <div class="wrap">
      <div class="player" [style.width.px]="size" [style.height.px]="size">
        @if (currentUrl) {
          <img
            [src]="currentUrl"
            [alt]="label"
            draggable="false"
            [appLightbox]="currentUrl"
            [appLightboxItems]="frameList"
            [appLightboxIndex]="idx"
            [appLightboxAlt]="label"
            [appLightboxCaption]="label + ' · frame ' + (idx + 1)"
          />
        } @else {
          <div class="empty">no frames</div>
        }
      </div>
      <div class="controls">
        <button type="button" class="btn" (click)="toggle()" [disabled]="frameList.length <= 1">
          {{ isPlaying ? 'Pause' : 'Play' }}
        </button>
        <label class="speed">
          <span class="speed-label">{{ playbackFps }} fps</span>
          <input
            type="range"
            min="1"
            max="30"
            step="1"
            [value]="playbackFps"
            (input)="onSpeedInput($event)"
            (change)="onSpeedCommit()"
            [disabled]="frameList.length <= 1"
            aria-label="Playback speed"
          />
        </label>
        <span class="meta">{{ frameList.length }}f · #{{ idx + 1 }}</span>
      </div>
    </div>
  `,
  styles: [
    `
      .wrap {
        display: grid;
        gap: 0.35rem;
        width: max-content;
        max-width: 100%;
      }
      .player {
        image-rendering: pixelated;
        background: #1c1f24;
        border: 1px solid rgba(255, 255, 255, 0.08);
        display: grid;
        place-items: center;
        overflow: hidden;
      }
      img {
        width: 100%;
        height: 100%;
        object-fit: contain;
        image-rendering: pixelated;
      }
      .empty {
        color: #8b929c;
        font-size: 0.8rem;
      }
      .controls {
        display: flex;
        align-items: center;
        gap: 0.55rem;
        width: 100%;
        flex-wrap: wrap;
      }
      .speed {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        flex: 1 1 7rem;
        min-width: 0;
        font-size: 0.75rem;
        color: #8b929c;
      }
      .speed-label {
        flex: 0 0 auto;
        min-width: 3.2rem;
        font-variant-numeric: tabular-nums;
      }
      .speed input[type='range'] {
        flex: 1 1 auto;
        min-width: 0;
        margin: 0;
        accent-color: var(--accent, #c9a46a);
        cursor: pointer;
      }
      .speed input[type='range']:disabled {
        opacity: 0.4;
        cursor: default;
      }
      .meta {
        color: #8b929c;
        font-size: 0.75rem;
        margin-left: auto;
      }
      .btn {
        font: inherit;
        font-size: 0.75rem;
        padding: 0.25rem 0.55rem;
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.12);
        color: inherit;
        cursor: pointer;
      }
      .btn:disabled {
        opacity: 0.4;
        cursor: default;
      }
    `,
  ],
})
export class SpritePlayerComponent implements OnChanges, OnDestroy {
  private readonly zone = inject(NgZone);

  @Input() frames: string[] = [];
  @Input() fps = 8;
  @Input() size = 160;
  @Input() label = 'sprite';
  @Input() playing = false;
  /** When true, speed slider stays enabled and fires fpsChange on commit. */
  @Input() persistSpeed = false;
  @Output() fpsChange = new EventEmitter<number>();

  frameList: string[] = [];
  currentUrl = '';
  idx = 0;
  isPlaying = false;
  playbackFps = 8;
  private timer: ReturnType<typeof setInterval> | null = null;
  private framesKey = '';
  private speedTouched = false;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['frames']) {
      const next = Array.isArray(this.frames) ? this.frames.filter(Boolean) : [];
      const key = next.join('\n');
      if (key !== this.framesKey) {
        this.framesKey = key;
        this.frameList = next;
        this.idx = 0;
        this.currentUrl = this.frameList[0] || '';
      }
    }
    if (changes['fps'] && !this.speedTouched) {
      this.playbackFps = this.clampFps(this.fps);
    }
    if (changes['playing'] && changes['playing'].currentValue !== undefined) {
      this.isPlaying = !!this.playing;
    }
    if (changes['frames'] || changes['fps'] || changes['playing']) {
      this.syncTimer();
    }
  }

  ngOnDestroy(): void {
    this.clearTimer();
  }

  toggle(): void {
    this.isPlaying = !this.isPlaying;
    this.syncTimer();
  }

  onSpeedInput(event: Event): void {
    const value = Number((event.target as HTMLInputElement).value);
    this.speedTouched = true;
    this.playbackFps = this.clampFps(value);
    this.syncTimer();
  }

  onSpeedCommit(): void {
    if (!this.persistSpeed) {
      return;
    }
    this.fpsChange.emit(this.playbackFps);
  }

  private clampFps(value: number): number {
    if (!Number.isFinite(value)) {
      return 8;
    }
    return Math.min(30, Math.max(1, Math.round(value)));
  }

  private syncTimer(): void {
    this.clearTimer();
    if (!this.isPlaying || this.frameList.length <= 1) {
      return;
    }
    const ms = Math.max(33, Math.round(1000 / Math.max(1, this.playbackFps)));
    // Run outside Angular, push UI updates back in — avoids CD thrash/restarts
    this.zone.runOutsideAngular(() => {
      this.timer = setInterval(() => {
        this.idx = (this.idx + 1) % this.frameList.length;
        const url = this.frameList[this.idx];
        this.zone.run(() => {
          this.currentUrl = url;
        });
      }, ms);
    });
  }

  private clearTimer(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }
}
