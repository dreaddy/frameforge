import { Directive, HostListener, Input, inject } from '@angular/core';
import { LightboxItem, LightboxService } from '../services/lightbox.service';

@Directive({
  selector: '[appLightbox]',
  standalone: true,
  host: {
    class: 'lightbox-trigger',
    '[attr.role]': '"button"',
    '[attr.tabindex]': '0',
    '[attr.title]': 'title || "View larger"',
  },
})
export class LightboxDirective {
  private readonly lightbox = inject(LightboxService);

  /** Primary image URL (required). */
  @Input({ alias: 'appLightbox', required: true }) src!: string;

  /** Optional gallery of URLs or items; defaults to [src]. */
  @Input('appLightboxItems') items: Array<string | LightboxItem> | null = null;

  /** Index within gallery. */
  @Input('appLightboxIndex') index = 0;

  @Input('appLightboxAlt') alt = '';
  @Input('appLightboxCaption') caption = '';
  @Input('appLightboxTitle') title = 'View larger';

  @HostListener('click', ['$event'])
  onClick(event: Event): void {
    event.preventDefault();
    event.stopPropagation();
    this.open();
  }

  @HostListener('keydown.enter', ['$event'])
  @HostListener('keydown.space', ['$event'])
  onKey(event: Event): void {
    event.preventDefault();
    event.stopPropagation();
    this.open();
  }

  private open(): void {
    const src = (this.src || '').trim();
    if (!src) {
      return;
    }
    const gallery = this.items?.length
      ? this.items
      : [{ src, alt: this.alt, caption: this.caption }];
    this.lightbox.open(gallery, this.index || 0);
  }
}
