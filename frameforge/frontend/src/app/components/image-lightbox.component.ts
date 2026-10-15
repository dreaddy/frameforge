import { AsyncPipe } from '@angular/common';
import { Component, HostListener, inject } from '@angular/core';
import { LightboxService } from '../services/lightbox.service';

@Component({
  selector: 'app-image-lightbox',
  standalone: true,
  imports: [AsyncPipe],
  template: `
    @if (lightbox.state$ | async; as state) {
      @if (state.open) {
        <div
          class="backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Image preview"
          (click)="lightbox.close()"
        >
          <button type="button" class="close" (click)="lightbox.close()" aria-label="Close">
            ×
          </button>
          @if (state.items.length > 1) {
            <button
              type="button"
              class="nav prev"
              (click)="prev($event)"
              aria-label="Previous image"
            >
              ‹
            </button>
            <button type="button" class="nav next" (click)="next($event)" aria-label="Next image">
              ›
            </button>
          }
          <figure class="stage" (click)="$event.stopPropagation()">
            <img
              [src]="state.items[state.index].src"
              [alt]="state.items[state.index].alt || 'Preview'"
            />
            @if (state.items[state.index].caption || state.items.length > 1) {
              <figcaption>
                @if (state.items[state.index].caption) {
                  <span>{{ state.items[state.index].caption }}</span>
                }
                @if (state.items.length > 1) {
                  <span class="count">{{ state.index + 1 }} / {{ state.items.length }}</span>
                }
              </figcaption>
            }
          </figure>
        </div>
      }
    }
  `,
  styles: [
    `
      .backdrop {
        position: fixed;
        inset: 0;
        z-index: 2000;
        background: rgba(6, 8, 12, 0.88);
        backdrop-filter: blur(4px);
        display: grid;
        place-items: center;
        padding: 2.5rem 3.5rem;
        animation: fade-in 0.16s ease;
      }
      @keyframes fade-in {
        from {
          opacity: 0;
        }
        to {
          opacity: 1;
        }
      }
      .stage {
        margin: 0;
        max-width: min(96vw, 1100px);
        max-height: calc(100vh - 4rem);
        display: grid;
        gap: 0.65rem;
        justify-items: center;
      }
      .stage img {
        max-width: 100%;
        max-height: calc(100vh - 6.5rem);
        object-fit: contain;
        image-rendering: pixelated;
        background:
          linear-gradient(45deg, #2a2a32 25%, transparent 25%),
          linear-gradient(-45deg, #2a2a32 25%, transparent 25%),
          linear-gradient(45deg, transparent 75%, #2a2a32 75%),
          linear-gradient(-45deg, transparent 75%, #2a2a32 75%);
        background-size: 16px 16px;
        background-position: 0 0, 0 8px, 8px -8px, -8px 0;
        background-color: #1a1a20;
        box-shadow: 0 18px 60px rgba(0, 0, 0, 0.45);
      }
      figcaption {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        justify-content: center;
        color: var(--muted);
        font-size: 0.9rem;
      }
      .count {
        color: rgba(243, 239, 230, 0.75);
      }
      .close,
      .nav {
        position: absolute;
        border: 1px solid rgba(255, 255, 255, 0.14);
        background: rgba(0, 0, 0, 0.35);
        color: var(--ink);
        cursor: pointer;
        font: inherit;
        line-height: 1;
      }
      .close {
        top: 1rem;
        right: 1rem;
        width: 2.4rem;
        height: 2.4rem;
        font-size: 1.6rem;
      }
      .nav {
        top: 50%;
        transform: translateY(-50%);
        width: 2.6rem;
        height: 2.6rem;
        font-size: 1.8rem;
      }
      .nav.prev {
        left: 0.75rem;
      }
      .nav.next {
        right: 0.75rem;
      }
      .close:hover,
      .nav:hover {
        border-color: rgba(255, 196, 120, 0.45);
      }
    `,
  ],
})
export class ImageLightboxComponent {
  readonly lightbox = inject(LightboxService);

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.lightbox.close();
  }

  @HostListener('document:keydown.arrowright')
  onRight(): void {
    if (this.lightbox.state.open) {
      this.lightbox.next();
    }
  }

  @HostListener('document:keydown.arrowleft')
  onLeft(): void {
    if (this.lightbox.state.open) {
      this.lightbox.prev();
    }
  }

  next(event: Event): void {
    event.stopPropagation();
    this.lightbox.next();
  }

  prev(event: Event): void {
    event.stopPropagation();
    this.lightbox.prev();
  }
}
