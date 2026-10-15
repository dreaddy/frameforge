import { Routes } from '@angular/router';
import { CharacterDetailPage } from './pages/character-detail.page';
import { GalleryPage } from './pages/gallery.page';
import { GeneratePage } from './pages/generate.page';
import { ItemDetailPage } from './pages/item-detail.page';
import { ProjectsPage } from './pages/projects.page';

export const routes: Routes = [
  { path: '', component: GalleryPage },
  { path: 'generate', component: GeneratePage, data: { assetKind: 'creature' } },
  { path: 'generate-item', component: GeneratePage, data: { assetKind: 'item' } },
  { path: 'projects', component: ProjectsPage },
  { path: 'characters/:id', component: CharacterDetailPage },
  { path: 'items/:id', component: ItemDetailPage },
  { path: '**', redirectTo: '' },
];
