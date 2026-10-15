import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

export interface LightboxItem {
  src: string;
  alt?: string;
  caption?: string;
}

export interface LightboxState {
  open: boolean;
  items: LightboxItem[];
  index: number;
}

@Injectable({ providedIn: 'root' })
export class LightboxService {
  private readonly stateSubject = new BehaviorSubject<LightboxState>({
    open: false,
    items: [],
    index: 0,
  });

  readonly state$ = this.stateSubject.asObservable();

  get state(): LightboxState {
    return this.stateSubject.value;
  }

  open(items: Array<string | LightboxItem>, index = 0): void {
    const normalized = items
      .map((item) => (typeof item === 'string' ? { src: item } : item))
      .filter((item) => !!item.src);
    if (!normalized.length) {
      return;
    }
    const safeIndex = Math.max(0, Math.min(index, normalized.length - 1));
    this.stateSubject.next({ open: true, items: normalized, index: safeIndex });
  }

  openOne(src: string, alt = '', caption = ''): void {
    this.open([{ src, alt, caption }], 0);
  }

  close(): void {
    if (!this.state.open) {
      return;
    }
    this.stateSubject.next({ open: false, items: [], index: 0 });
  }

  next(): void {
    const { open, items, index } = this.state;
    if (!open || items.length < 2) {
      return;
    }
    this.stateSubject.next({ open, items, index: (index + 1) % items.length });
  }

  prev(): void {
    const { open, items, index } = this.state;
    if (!open || items.length < 2) {
      return;
    }
    this.stateSubject.next({
      open,
      items,
      index: (index - 1 + items.length) % items.length,
    });
  }
}
