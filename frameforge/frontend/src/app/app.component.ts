import { AsyncPipe } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ImageLightboxComponent } from './components/image-lightbox.component';
import { ProjectContextService } from './services/project-context.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    FormsModule,
    AsyncPipe,
    ImageLightboxComponent,
  ],
  template: `
    <div class="shell">
      <header class="topbar">
        <a routerLink="/" class="logo">Frameforge</a>
        <nav aria-label="Main">
          <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }"
            >Library</a
          >
          <a routerLink="/generate" routerLinkActive="active">New creature</a>
          <a routerLink="/generate-item" routerLinkActive="active">New item</a>
          <a routerLink="/projects" routerLinkActive="active">Projects</a>
        </nav>
        <label class="project-pick" title="Active game project">
          <span>Project</span>
          <select [ngModel]="ctx.activeProjectId" (ngModelChange)="onProjectChange($event)">
            @for (p of ctx.projects$ | async; track p.id) {
              <option [ngValue]="p.id">{{ p.name }}</option>
            }
          </select>
        </label>
      </header>
      <main>
        <router-outlet />
      </main>
    </div>
    <app-image-lightbox />
  `,
  styles: [
    `
      .shell {
        min-height: 100vh;
      }
      .topbar {
        width: min(1100px, calc(100% - 2rem));
        margin: 0 auto;
        display: grid;
        grid-template-columns: auto 1fr auto;
        align-items: center;
        gap: 1.25rem 1.75rem;
        padding: 0.95rem 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      }
      @media (max-width: 720px) {
        .topbar {
          grid-template-columns: 1fr auto;
        }
        nav {
          grid-column: 1 / -1;
          order: 3;
        }
      }
      .logo {
        font-family: var(--font-display);
        font-size: 1.45rem;
        text-decoration: none;
        color: var(--ink);
        letter-spacing: -0.02em;
        white-space: nowrap;
      }
      nav {
        display: flex;
        align-items: center;
        gap: 0.35rem;
        flex-wrap: wrap;
      }
      nav a {
        color: var(--muted);
        text-decoration: none;
        padding: 0.45rem 0.85rem;
        border: 1px solid transparent;
        font-weight: 500;
        font-size: 0.95rem;
        transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
      }
      nav a:hover {
        color: var(--ink);
      }
      nav a.active {
        color: var(--ink);
        border-color: rgba(255, 196, 120, 0.4);
        background: rgba(255, 196, 120, 0.1);
      }
      .project-pick {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        color: var(--muted);
        font-size: 0.85rem;
        justify-self: end;
      }
      .project-pick select {
        background: rgba(0, 0, 0, 0.28);
        border: 1px solid rgba(255, 255, 255, 0.12);
        color: var(--ink);
        padding: 0.4rem 0.6rem;
        font: inherit;
        max-width: 14rem;
      }
      main {
        width: min(1100px, calc(100% - 2rem));
        margin: 0 auto;
      }
    `,
  ],
})
export class AppComponent implements OnInit {
  readonly ctx = inject(ProjectContextService);

  ngOnInit(): void {
    void this.ctx.refresh();
  }

  onProjectChange(id: string): void {
    this.ctx.setActiveProjectId(id);
  }
}
