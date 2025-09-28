export function normalizeText(s: string) {
  if (!s) return '';
  const rep: Record<string, string> = {
    '≫': '>>', '«': '<<', '»': '>>', '♪': ' note ',
    '☆': '*', '★': '*', '　': ' ',
    '–': '-', '—': '-', '―': '-', '…': '...',
  };
  let s2 = s.trim().toLowerCase();
  for (const [k, v] of Object.entries(rep)) s2 = s2.split(k).join(v);
  return s2.replace(/\s{2,}/g, ' ');
}

export function buildEventKey(params: {
  type: 'support'|'trainee'|'scenario';
  name: string;
  attribute?: string;   // support only
  rarity?: string;      // support only
  eventName: string;
  chainStep?: number;
}) {
  const step = (params.chainStep ?? 1);
  if (params.type === 'support') {
    const attr = params.attribute ?? 'None';
    const rar  = params.rarity ?? 'None';
    return `support/${params.name}/${attr}/${rar}/${params.eventName}#s${step}`;
  }
  if (params.type === 'scenario') {
    return `scenario/${params.name}/None/None/${params.eventName}#s${step}`;
  }
  return `trainee/${params.name}/None/None/${params.eventName}#s${step}`;
}
