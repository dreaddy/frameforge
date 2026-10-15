import { Component, EventEmitter, Input, Output } from '@angular/core';
import { ImageCroppedEvent, ImageCropperComponent, LoadedImage } from 'ngx-image-cropper';

@Component({
  selector: 'app-sprite-image-picker',
  standalone: true,
  imports: [ImageCropperComponent],
  template: `
    <div class="picker">
      <label class="file-btn">
        <input type="file" accept="image/*" (change)="onFileChange($event)" />
        {{ imageEvent ? 'Change image' : 'Choose image' }}
      </label>
      @if (fileName) {
        <span class="file-name">{{ fileName }}</span>
      }
      @if (imageEvent) {
        <div class="crop-wrap">
          <image-cropper
            [imageChangedEvent]="imageEvent"
            [maintainAspectRatio]="true"
            [aspectRatio]="1"
            [resizeToWidth]="512"
            [format]="'png'"
            [imageQuality]="100"
            [onlyScaleDown]="true"
            [backgroundColor]="'transparent'"
            (imageCropped)="onCropped($event)"
            (imageLoaded)="onLoaded($event)"
            (loadImageFailed)="onLoadFailed()"
          />
        </div>
        <p class="hint">Drag to frame a square crop. Export size is applied on save.</p>
      }
      @if (error) {
        <p class="error">{{ error }}</p>
      }
    </div>
  `,
  styles: [
    `
      .picker {
        display: grid;
        gap: 0.65rem;
      }
      .file-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: fit-content;
        border: 1px solid rgba(255, 255, 255, 0.14);
        background: rgba(255, 255, 255, 0.04);
        color: var(--ink);
        padding: 0.55rem 0.9rem;
        font: inherit;
        cursor: pointer;
      }
      .file-btn input {
        display: none;
      }
      .file-name {
        color: var(--muted);
        font-size: 0.85rem;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .crop-wrap {
        border: 1px solid rgba(255, 255, 255, 0.08);
        background: rgba(0, 0, 0, 0.28);
        max-height: 22rem;
        overflow: hidden;
      }
      .crop-wrap ::ng-deep image-cropper {
        max-height: 22rem;
      }
      .hint {
        margin: 0;
        color: var(--muted);
        font-size: 0.8rem;
      }
      .error {
        margin: 0;
        color: #ff8f8f;
        font-size: 0.85rem;
      }
    `,
  ],
})
export class SpriteImagePickerComponent {
  @Input() disabled = false;
  @Output() readonly croppedChange = new EventEmitter<Blob | null>();

  imageEvent: Event | null = null;
  fileName = '';
  error = '';

  onFileChange(event: Event): void {
    if (this.disabled) {
      return;
    }
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    this.error = '';
    this.fileName = file?.name || '';
    this.imageEvent = file ? event : null;
    if (!file) {
      this.croppedChange.emit(null);
    }
  }

  onCropped(event: ImageCroppedEvent): void {
    this.croppedChange.emit(event.blob ?? null);
  }

  onLoaded(_image: LoadedImage): void {
    this.error = '';
  }

  onLoadFailed(): void {
    this.error = 'Could not load that image.';
    this.croppedChange.emit(null);
  }

  clear(): void {
    this.imageEvent = null;
    this.fileName = '';
    this.error = '';
    this.croppedChange.emit(null);
  }

  /** Prefill cropper from an existing sprite URL (e.g. recreate flow). */
  async loadFromUrl(url: string, fileName = 'reference.png'): Promise<void> {
    if (this.disabled) {
      return;
    }
    this.error = '';
    try {
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const type = blob.type || 'image/png';
      const file = new File([blob], fileName, { type });
      const input = document.createElement('input');
      input.type = 'file';
      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      const event = new Event('change', { bubbles: true });
      Object.defineProperty(event, 'target', { value: input });
      this.onFileChange(event);
    } catch {
      this.error = 'Could not load reference image.';
      this.croppedChange.emit(null);
    }
  }
}
