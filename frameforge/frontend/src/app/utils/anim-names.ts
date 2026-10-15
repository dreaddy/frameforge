/** Match backend animation_names.py — idle, idle2, idle3, … */

export function sanitizeAnimName(raw: string): string {
  let s = (raw || '').trim().toLowerCase().replace(/\s+/g, '_');
  s = s.replace(/[^a-z0-9_-]/g, '_');
  while (s.includes('__')) {
    s = s.replace(/__/g, '_');
  }
  s = s.replace(/^_+|_+$/g, '');
  return s || 'anim';
}

export function nextAnimName(base: string, existing: string[]): string {
  const root = sanitizeAnimName(base);
  const taken = new Set(existing.map(sanitizeAnimName).filter(Boolean));
  if (!taken.has(root)) {
    return root;
  }
  let i = 2;
  while (taken.has(`${root}${i}`)) {
    i += 1;
  }
  return `${root}${i}`;
}

export function animLabel(entry: { name?: string; type: string; ref?: number }): string {
  const name = (entry.name || entry.type || '').trim() || 'anim';
  return entry.ref != null ? `#${entry.ref} ${name}` : name;
}
