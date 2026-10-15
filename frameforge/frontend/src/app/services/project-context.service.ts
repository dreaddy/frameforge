import { Injectable, inject } from '@angular/core';
import { BehaviorSubject, Observable, firstValueFrom } from 'rxjs';
import { ApiService, GameProject } from './api.service';

const STORAGE_KEY = 'frameforge.activeProjectId';

@Injectable({ providedIn: 'root' })
export class ProjectContextService {
  private readonly api = inject(ApiService);
  private readonly projectsSubject = new BehaviorSubject<GameProject[]>([]);
  private readonly activeIdSubject = new BehaviorSubject<string | null>(
    localStorage.getItem(STORAGE_KEY)
  );

  readonly projects$: Observable<GameProject[]> = this.projectsSubject.asObservable();
  readonly activeProjectId$: Observable<string | null> = this.activeIdSubject.asObservable();

  get projects(): GameProject[] {
    return this.projectsSubject.value;
  }

  get activeProjectId(): string | null {
    return this.activeIdSubject.value;
  }

  get activeProject(): GameProject | null {
    const id = this.activeProjectId;
    if (!id) {
      return null;
    }
    return this.projects.find((p) => p.id === id) ?? null;
  }

  async refresh(): Promise<GameProject[]> {
    const list = await firstValueFrom(this.api.listProjects());
    this.projectsSubject.next(list);
    const current = this.activeProjectId;
    if (current && list.some((p) => p.id === current)) {
      return list;
    }
    const next = list[0]?.id ?? null;
    this.setActiveProjectId(next);
    return list;
  }

  setActiveProjectId(id: string | null): void {
    if (id) {
      localStorage.setItem(STORAGE_KEY, id);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    this.activeIdSubject.next(id);
  }
}
