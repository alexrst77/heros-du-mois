/* Éditeur d'avatars « Mon Héros du Mois » : enfant, doudou et animaux dessinés en SVG. */
(function (g) {
  let OPT = null, UID = 0;
  const pick = (list, id) => list.find(o => o.id === id) || list[0];
  function shade(hex, f) {
    const n = parseInt(hex.slice(1), 16);
    let r = n >> 16, gg = (n >> 8) & 255, b = n & 255;
    const t = f < 0 ? 0 : 255, p = Math.abs(f);
    r = Math.round((t - r) * p + r); gg = Math.round((t - gg) * p + gg); b = Math.round((t - b) * p + b);
    return '#' + ((1 << 24) + (r << 16) + (gg << 8) + b).toString(16).slice(1);
  }
  const star = (x, y, r, fill) => {
    let d = '';
    for (let i = 0; i < 10; i++) {
      const a = -Math.PI / 2 + i * Math.PI / 5, rr = i % 2 ? r * .45 : r;
      d += (i ? 'L' : 'M') + (x + rr * Math.cos(a)).toFixed(1) + ',' + (y + rr * Math.sin(a)).toFixed(1);
    }
    return `<path d="${d}Z" fill="${fill}" stroke="${fill}" stroke-width="1.2" stroke-linejoin="round"/>`;
  };

  /* ---------------- ENFANT ---------------- */
  function child(e, view) {
    const O = OPT.enfant, id = 'a' + (++UID);
    const skin = pick(O.peau, e.peau), hair = pick(O.couleur_cheveux, e.couleur_cheveux).c, hs = shade(hair, -.28);
    const eye = pick(O.yeux, e.yeux).c, oc = pick(O.couleur_tenue, e.couleur_tenue).c, ocd = shade(oc, -.22);
    const gl = pick(O.couleur_lunettes, e.couleur_lunettes).c, style = e.coiffure, S = skin.c, SH = skin.sh;
    let back = '', front = '';
    const cap = `<path d="M82,150 C78,96 108,66 150,66 C192,66 222,96 218,150 C212,122 200,108 188,102 C170,114 132,112 112,102 C100,110 88,126 82,150 Z" fill="${hair}"/>`;
    const swept = `<path d="M84,142 C80,92 110,66 150,66 C190,66 220,92 216,142 C210,112 190,96 150,94 C118,96 96,112 84,142 Z" fill="${hair}"/>`;
    const curls = (pts, r, fill) => pts.map(p => `<circle cx="${p[0]}" cy="${p[1]}" r="${p[2] || r}" fill="${fill}"/>`).join('');
    const arc = (cx, cy, rx, ry, a0, a1, n) => { const o = []; for (let i = 0; i <= n; i++) { const a = a0 + (a1 - a0) * i / n; o.push([cx + rx * Math.cos(a), cy + ry * Math.sin(a)]); } return o; };
    switch (style) {
      case 'rase':
        front = `<path d="M86,138 C86,92 112,72 150,72 C188,72 214,92 214,138 C204,110 184,98 150,98 C116,98 96,110 86,138 Z" fill="${hair}" opacity=".85"/>`; break;
      case 'court': front = cap; break;
      case 'bataille':
        front = cap + `<path d="M98,92 L92,60 L116,80 L120,50 L138,74 L150,42 L162,72 L180,50 L184,80 L208,62 L204,94 Z" fill="${hair}"/>` +
          `<path d="M110,100 L118,124 L128,104 Z M140,106 L150,126 L158,106 Z M170,104 L182,122 L188,100 Z" fill="${hair}"/>`; break;
      case 'boucle':
        front = cap + curls(arc(150, 128, 70, 64, Math.PI * 1.02, Math.PI * 1.98, 9), 19, hair) +
          curls([[112, 104, 15], [132, 100, 15], [152, 98, 15], [172, 100, 15], [190, 106, 14]], 15, hair) +
          curls(arc(150, 128, 58, 54, Math.PI * 1.15, Math.PI * 1.85, 5).map(p => [p[0], p[1], 5]), 5, shade(hair, .12)); break;
      case 'afro':
        back = `<circle cx="150" cy="118" r="98" fill="${hair}"/>` + curls(arc(150, 118, 96, 96, 0, Math.PI * 2, 22), 20, hair);
        front = curls([[104, 108, 18], [124, 98, 18], [150, 94, 19], [176, 98, 18], [196, 108, 18]], 18, hair); break;
      case 'carre':
        back = `<path d="M74,150 C68,82 104,58 150,58 C196,58 232,82 226,150 L228,208 C214,216 198,214 190,208 L110,208 C102,214 86,216 72,208 Z" fill="${hair}"/>`;
        front = `<path d="M86,132 C86,90 112,68 150,68 C188,68 214,90 214,132 C212,120 206,116 198,116 L102,116 C94,116 88,120 86,132 Z" fill="${hair}"/>` +
          `<path d="M84,124 C78,160 80,192 86,210 L106,210 C98,180 98,150 104,124 Z" fill="${hair}"/><path d="M216,124 C222,160 220,192 214,210 L194,210 C202,180 202,150 196,124 Z" fill="${hair}"/>`; break;
      case 'long':
        back = `<path d="M76,150 C68,80 106,56 150,56 C194,56 232,80 224,150 L230,260 L70,260 Z" fill="${hs}"/>`;
        front = `<path d="M84,138 C82,90 110,66 150,66 C190,66 218,90 216,138 C206,110 186,98 160,96 C140,104 112,108 96,118 C90,124 86,130 84,138 Z" fill="${hair}"/>` +
          `<path d="M86,118 C74,170 78,240 70,300 C84,310 98,306 106,296 C100,240 98,180 104,122 Z" fill="${hair}"/><path d="M214,118 C226,170 222,240 230,300 C216,310 202,306 194,296 C200,240 202,180 196,122 Z" fill="${hair}"/>`; break;
      case 'longboucle':
        back = `<path d="M70,150 C62,78 104,52 150,52 C196,52 238,78 230,150 L238,262 L62,262 Z" fill="${hs}"/>`;
        front = cap + curls(arc(150, 128, 70, 64, Math.PI * 1.02, Math.PI * 1.98, 9), 18, hair);
        for (let y = 130, i = 0; y <= 300; y += 17, i++) {
          const dx = i % 2 ? 6 : 0;
          front += `<circle cx="${86 - dx}" cy="${y}" r="17" fill="${hair}"/><circle cx="${214 + dx}" cy="${y}" r="17" fill="${hair}"/>`;
        } break;
      case 'couettes':
        back = `<ellipse cx="62" cy="170" rx="26" ry="38" transform="rotate(-18 62 170)" fill="${hair}"/><ellipse cx="238" cy="170" rx="26" ry="38" transform="rotate(18 238 170)" fill="${hair}"/>`;
        front = cap + `<circle cx="84" cy="140" r="8" fill="${oc}"/><circle cx="216" cy="140" r="8" fill="${oc}"/>`; break;
      case 'queue':
        back = `<path d="M168,70 C232,58 256,112 240,172 C232,204 214,220 204,232 C214,198 216,160 194,118 Z" fill="${hair}"/>`;
        front = swept + `<circle cx="186" cy="74" r="8" fill="${oc}"/>`; break;
      case 'tresses':
        front = `<path d="M84,142 C80,92 110,66 150,66 C190,66 220,92 216,142 C208,112 186,98 154,98 L150,74 L146,98 C114,98 92,112 84,142 Z" fill="${hair}"/>`;
        for (let y = 160, i = 0; y <= 286; y += 18, i++) {
          const dx = i % 2 ? 3 : -3;
          front += `<ellipse cx="${90 + dx}" cy="${y}" rx="14" ry="11" fill="${hair}" stroke="${hs}" stroke-width="2"/><ellipse cx="${210 - dx}" cy="${y}" rx="14" ry="11" fill="${hair}" stroke="${hs}" stroke-width="2"/>`;
        }
        front += `<circle cx="90" cy="300" r="6" fill="${oc}"/><circle cx="210" cy="300" r="6" fill="${oc}"/>`; break;
      case 'chignon':
        back = `<circle cx="150" cy="58" r="32" fill="${hair}"/>`;
        front = swept + `<path d="M126,82 Q150,72 174,82" stroke="${oc}" stroke-width="7" fill="none" stroke-linecap="round"/>`; break;
      default: front = cap;
    }

    // tenue
    const body = 'M52,340 C54,270 84,244 122,236 L178,236 C216,244 246,270 248,340 Z';
    let outfit = '';
    switch (e.tenue) {
      case 'pyjama':
        outfit = `<path d="${body}" fill="${oc}"/>` + [[92, 290], [150, 306], [206, 284], [120, 330], [184, 326], [74, 326], [226, 322], [150, 270]].map(p => star(p[0], p[1], 7, '#FFF7E0')).join('') +
          `<path d="M122,237 Q150,262 178,237" stroke="${ocd}" stroke-width="6" fill="none" stroke-linecap="round"/>`; break;
      case 'salopette':
        outfit = `<path d="${body}" fill="#F3F1EC"/><path d="M122,237 Q150,256 178,237" stroke="#D9D5CC" stroke-width="5" fill="none"/>` +
          `<path d="M104,272 L196,272 L204,340 L96,340 Z" fill="${oc}"/><path d="M118,238 L112,276 M182,238 L188,276" stroke="${oc}" stroke-width="13" stroke-linecap="round"/>` +
          `<circle cx="114" cy="282" r="5" fill="#F2D27A"/><circle cx="186" cy="282" r="5" fill="#F2D27A"/><rect x="130" y="292" width="40" height="26" rx="6" fill="${ocd}"/>`; break;
      case 'sweat':
        outfit = `<path d="${body}" fill="${oc}"/><path d="M110,236 Q150,222 190,236 Q178,262 150,264 Q122,262 110,236 Z" fill="${ocd}"/>` +
          `<path d="M140,262 L137,296 M160,262 L163,296" stroke="#FFF" stroke-width="3" stroke-linecap="round"/><rect x="112" y="304" width="76" height="36" rx="12" fill="${ocd}" opacity=".7"/>`; break;
      case 'robe':
        outfit = `<path d="${body}" fill="${oc}"/><path d="M120,236 Q124,262 150,252 Q176,262 180,236 Z" fill="#FFFDF7"/><circle cx="150" cy="276" r="4" fill="#FFFDF7"/><circle cx="150" cy="296" r="4" fill="#FFFDF7"/>`; break;
      case 'mariniere':
        outfit = `<clipPath id="${id}b"><path d="${body}"/></clipPath><path d="${body}" fill="#F7F4EE"/><g clip-path="url(#${id}b)" fill="${oc}">` +
          [254, 274, 294, 314, 334].map(y => `<rect x="40" y="${y}" width="220" height="9"/>`).join('') + `</g><path d="M122,237 Q150,256 178,237" stroke="${ocd}" stroke-width="5" fill="none"/>`; break;
      default:
        outfit = `<path d="${body}" fill="${oc}"/><path d="M122,237 Q150,258 178,237" stroke="${ocd}" stroke-width="6" fill="none" stroke-linecap="round"/>`;
    }

    // visage
    const eyes = [124, 176].map(x => `<circle cx="${x}" cy="152" r="9.5" fill="${eye}"/><circle cx="${x}" cy="152" r="5.2" fill="#1D1410"/><circle cx="${x + 3}" cy="148.5" r="2.8" fill="#FFF"/>`).join('');
    const lashes = e.genre === 'fille' ? `<path d="M115,146 L109,140 M185,146 L191,140" stroke="#1D1410" stroke-width="3" stroke-linecap="round"/>` : '';
    const brows = `<path d="M110,131 Q124,123 138,130 M162,130 Q176,123 190,131" stroke="${hs}" stroke-width="4.5" fill="none" stroke-linecap="round"/>`;
    const freck = e.taches === 'oui' ? [[102, 170], [110, 175], [116, 168], [184, 168], [190, 175], [198, 170]].map(p => `<circle cx="${p[0]}" cy="${p[1]}" r="1.9" fill="${shade(SH, -.25)}"/>`).join('') : '';
    const face = eyes + lashes + brows +
      `<ellipse cx="108" cy="182" rx="12" ry="7" fill="#F2837E" opacity=".32"/><ellipse cx="192" cy="182" rx="12" ry="7" fill="#F2837E" opacity=".32"/>` + freck +
      `<path d="M146,171 Q150,176 154,171" stroke="${SH}" stroke-width="3" fill="none" stroke-linecap="round"/>` +
      `<path d="M134,186 Q150,202 166,186 Q150,194 134,186 Z" fill="#8A3530" stroke="#8A3530" stroke-width="3" stroke-linejoin="round"/>`;
    let glasses = '';
    if (e.lunettes === 'rondes') glasses = `<g stroke="${gl}" stroke-width="4.5" fill="#FFF" fill-opacity=".14"><circle cx="124" cy="152" r="21"/><circle cx="176" cy="152" r="21"/></g><path d="M145,150 Q150,145 155,150 M103,149 L86,145 M197,149 L214,145" stroke="${gl}" stroke-width="4" fill="none" stroke-linecap="round"/>`;
    if (e.lunettes === 'carrees') glasses = `<g stroke="${gl}" stroke-width="4.5" fill="#FFF" fill-opacity=".14"><rect x="101" y="136" width="46" height="32" rx="8"/><rect x="153" y="136" width="46" height="32" rx="8"/></g><path d="M147,150 L153,150 M101,148 L86,145 M199,148 L214,145" stroke="${gl}" stroke-width="4" fill="none" stroke-linecap="round"/>`;

    const vb = view === 'head' ? '46 22 208 220' : '0 0 300 340';
    return `<svg viewBox="${vb}" xmlns="http://www.w3.org/2000/svg">${back}${outfit}` +
      `<rect x="136" y="196" width="28" height="44" rx="10" fill="${SH}"/>` +
      `<circle cx="86" cy="152" r="13" fill="${S}"/><circle cx="214" cy="152" r="13" fill="${S}"/>` +
      `<ellipse cx="150" cy="142" rx="66" ry="70" fill="${S}"/>${face}${front}${glasses}</svg>`;
  }

  /* ---------------- DOUDOU & ANIMAUX ---------------- */
  function creature(a, kind) {
    const O = kind === 'doudou' ? OPT.doudou : OPT.animal, id = 'c' + (++UID);
    const col = pick(O.couleur, a.couleur), C = col.c, SH = col.sh;
    const plush = kind === 'doudou';
    const C2 = plush ? '#FFF6EA' : pick(O.couleur2, a.couleur2).c;
    const light = plush ? shade(C, .45) : (a.motif === 'ventre' || a.motif === 'uni' ? (a.motif === 'ventre' ? C2 : shade(C, .25)) : shade(C, .25));
    const eyeC = plush ? '#2A1C16' : pick(O.yeux, a.yeux).c;
    const t = a.type, droop = a.oreilles === 'tombantes';
    let behind = '', ears = '', extra = '', face = '', tail = '';
    let head = `<circle cx="150" cy="128" r="64" fill="${C}"/>`;
    let bodyShape = `<ellipse cx="150" cy="222" rx="68" ry="60" fill="${C}"/>`;
    const clipShapes = `<circle cx="150" cy="128" r="64"/><ellipse cx="150" cy="222" rx="68" ry="60"/>`;
    const pink = '#F3A7B5';
    const eyes = (y, sp) => [150 - sp, 150 + sp].map(x => plush
      ? `<circle cx="${x}" cy="${y}" r="7" fill="#2A1C16"/><circle cx="${x + 2.2}" cy="${y - 2.2}" r="2.2" fill="#FFF"/>`
      : `<circle cx="${x}" cy="${y}" r="10" fill="${eyeC}"/><circle cx="${x}" cy="${y}" r="5.5" fill="#1D1410"/><circle cx="${x + 3}" cy="${y - 3.4}" r="2.8" fill="#FFF"/>`).join('');
    const cheeks = `<ellipse cx="108" cy="150" rx="11" ry="6.5" fill="#F2837E" opacity=".3"/><ellipse cx="192" cy="150" rx="11" ry="6.5" fill="#F2837E" opacity=".3"/>`;
    switch (t) {
      case 'chat':
        ears = `<path d="M92,100 L96,40 L142,74 Z" fill="${C}"/><path d="M208,100 L204,40 L158,74 Z" fill="${C}"/><path d="M102,88 L104,56 L128,74 Z" fill="${pink}"/><path d="M198,88 L196,56 L172,74 Z" fill="${pink}"/>`;
        tail = `<path d="M210,250 C262,246 266,186 238,172" stroke="${C}" stroke-width="17" fill="none" stroke-linecap="round"/>`;
        face = eyes(124, 26) + `<path d="M143,142 L157,142 L150,150 Z" fill="${pink}"/><path d="M150,150 Q142,160 134,154 M150,150 Q158,160 166,154" stroke="#5A3A3A" stroke-width="3" fill="none" stroke-linecap="round"/>` +
          `<path d="M96,142 L66,136 M96,150 L66,152 M204,142 L234,136 M204,150 L234,152" stroke="${shade(C, -.35)}" stroke-width="2" stroke-linecap="round" opacity=".7"/>`; break;
      case 'chien': case 'puppy':
        ears = droop ? `<path d="M96,86 C58,88 56,160 80,182 C98,172 108,130 106,96 Z" fill="${SH}"/><path d="M204,86 C242,88 244,160 220,182 C202,172 192,130 194,96 Z" fill="${SH}"/>`
          : `<path d="M94,104 C88,70 96,46 110,40 C128,54 138,70 140,80 Z" fill="${C}"/><path d="M206,104 C212,70 204,46 190,40 C172,54 162,70 160,80 Z" fill="${C}"/><path d="M104,90 C102,70 106,58 112,54 C122,64 128,72 130,78 Z" fill="${pink}" opacity=".8"/><path d="M196,90 C198,70 194,58 188,54 C178,64 172,72 170,78 Z" fill="${pink}" opacity=".8"/>`;
        tail = `<path d="M212,236 C246,226 252,200 244,184" stroke="${C}" stroke-width="15" fill="none" stroke-linecap="round"/>`;
        face = eyes(120, 26) + `<ellipse cx="150" cy="156" rx="32" ry="24" fill="${light}"/><ellipse cx="150" cy="144" rx="12" ry="8.5" fill="#2A2020"/>` +
          `<path d="M150,152 L150,162 M150,162 Q140,170 132,164 M150,162 Q160,170 168,164" stroke="#4A2E2A" stroke-width="3" fill="none" stroke-linecap="round"/><path d="M144,168 Q150,184 156,168 Z" fill="#E8727C"/>`; break;
      case 'lapin':
        ears = droop ? `<ellipse cx="86" cy="138" rx="18" ry="52" transform="rotate(18 86 138)" fill="${C}"/><ellipse cx="214" cy="138" rx="18" ry="52" transform="rotate(-18 214 138)" fill="${C}"/><ellipse cx="88" cy="140" rx="9" ry="38" transform="rotate(18 88 140)" fill="${pink}"/><ellipse cx="212" cy="140" rx="9" ry="38" transform="rotate(-18 212 140)" fill="${pink}"/>`
          : `<ellipse cx="124" cy="54" rx="17" ry="48" transform="rotate(-8 124 54)" fill="${C}"/><ellipse cx="176" cy="54" rx="17" ry="48" transform="rotate(8 176 54)" fill="${C}"/><ellipse cx="124" cy="58" rx="8" ry="34" transform="rotate(-8 124 58)" fill="${pink}"/><ellipse cx="176" cy="58" rx="8" ry="34" transform="rotate(8 176 58)" fill="${pink}"/>`;
        tail = `<circle cx="214" cy="252" r="16" fill="${shade(C, .35)}"/>`;
        face = eyes(124, 26) + `<ellipse cx="150" cy="146" rx="7" ry="5.5" fill="${pink}"/><path d="M150,151 Q142,160 134,155 M150,151 Q158,160 166,155" stroke="#5A3A3A" stroke-width="3" fill="none" stroke-linecap="round"/><rect x="144" y="156" width="12" height="10" rx="2" fill="#FFF" stroke="#E2D8CC"/>`; break;
      case 'hamster':
        head = ''; bodyShape = `<ellipse cx="150" cy="182" rx="94" ry="96" fill="${C}"/>`;
        ears = `<circle cx="96" cy="102" r="20" fill="${C}"/><circle cx="204" cy="102" r="20" fill="${C}"/><circle cx="96" cy="104" r="11" fill="${pink}"/><circle cx="204" cy="104" r="11" fill="${pink}"/>`;
        extra = `<ellipse cx="150" cy="222" rx="60" ry="52" fill="${light}"/><ellipse cx="96" cy="176" rx="30" ry="24" fill="${light}"/><ellipse cx="204" cy="176" rx="30" ry="24" fill="${light}"/>` +
          `<ellipse cx="124" cy="206" rx="11" ry="8" fill="${pink}"/><ellipse cx="176" cy="206" rx="11" ry="8" fill="${pink}"/>`;
        face = eyes(140, 30) + `<ellipse cx="150" cy="160" rx="6" ry="4.5" fill="${pink}"/><path d="M150,164 Q143,172 136,168 M150,164 Q157,172 164,168" stroke="#5A3A3A" stroke-width="3" fill="none" stroke-linecap="round"/>`; break;
      case 'oiseau':
        head = ''; bodyShape = `<ellipse cx="150" cy="172" rx="84" ry="98" fill="${C}"/>`;
        ears = `<path d="M142,78 C132,52 140,40 150,36 C148,52 152,64 156,76 Z M156,76 C160,54 172,48 180,50 C170,60 166,70 164,82 Z" fill="${SH}"/>`;
        extra = `<ellipse cx="150" cy="210" rx="52" ry="56" fill="${a.motif === 'uni' ? shade(C, .3) : C2}"/><ellipse cx="72" cy="186" rx="22" ry="48" transform="rotate(14 72 186)" fill="${SH}"/><ellipse cx="228" cy="186" rx="22" ry="48" transform="rotate(-14 228 186)" fill="${SH}"/>` +
          `<path d="M130,268 L126,290 M126,290 L116,294 M126,290 L130,296 M170,268 L174,290 M174,290 L184,294 M174,290 L170,296" stroke="#E8963A" stroke-width="4.5" stroke-linecap="round"/>`;
        face = eyes(128, 28) + `<path d="M138,146 L162,146 L150,166 Z" fill="#F0A53A"/>`; break;
      case 'ours':
        ears = `<circle cx="98" cy="80" r="24" fill="${C}"/><circle cx="202" cy="80" r="24" fill="${C}"/><circle cx="98" cy="82" r="12" fill="${light}"/><circle cx="202" cy="82" r="12" fill="${light}"/>`;
        face = eyes(122, 26) + `<ellipse cx="150" cy="154" rx="30" ry="22" fill="${light}"/><ellipse cx="150" cy="144" rx="10" ry="7" fill="#3A2A26"/><path d="M150,151 L150,160 M150,160 Q142,168 134,162 M150,160 Q158,168 166,162" stroke="#4A2E2A" stroke-width="3" fill="none" stroke-linecap="round"/>`; break;
      case 'elephant':
        behind = `<ellipse cx="80" cy="132" rx="46" ry="54" fill="${SH}"/><ellipse cx="220" cy="132" rx="46" ry="54" fill="${SH}"/><ellipse cx="84" cy="134" rx="30" ry="38" fill="${pink}" opacity=".6"/><ellipse cx="216" cy="134" rx="30" ry="38" fill="${pink}" opacity=".6"/>`;
        face = eyes(118, 28) + `<path d="M150,138 C148,184 160,200 180,194" stroke="${C}" stroke-width="24" fill="none" stroke-linecap="round"/><path d="M150,140 C148,184 160,198 180,194" stroke="${SH}" stroke-width="3" fill="none" stroke-dasharray="2 9" stroke-linecap="round"/>`; break;
    }

    // motifs (animaux uniquement)
    let pattern = '';
    if (!plush && t !== 'oiseau') {
      const bodyClip = t === 'hamster' ? `<ellipse cx="150" cy="182" rx="94" ry="96"/>` : clipShapes;
      if (a.motif === 'ventre' && t !== 'hamster')
        pattern = `<ellipse cx="150" cy="234" rx="40" ry="44" fill="${C2}"/>` + (t === 'chat' || t === 'lapin' ? `<ellipse cx="150" cy="152" rx="30" ry="20" fill="${C2}"/>` : '');
      if (a.motif === 'taches')
        pattern = `<g clip-path="url(#${id}k)" fill="${C2}"><ellipse cx="116" cy="102" rx="30" ry="24"/><ellipse cx="200" cy="214" rx="30" ry="24"/><ellipse cx="116" cy="250" rx="22" ry="16"/></g>`;
      if (a.motif === 'raye')
        pattern = `<g clip-path="url(#${id}k)" stroke="${C2}" stroke-width="8" fill="none" stroke-linecap="round"><path d="M136,66 L140,86 M150,64 L150,88 M164,66 L160,86"/><path d="M84,200 Q100,206 104,222 M86,236 Q102,240 104,256 M216,200 Q200,206 196,222 M214,236 Q198,240 196,256"/></g>`;
      if (a.motif === 'masque')
        pattern = `<g clip-path="url(#${id}k)" fill="${C2}"><ellipse cx="122" cy="118" rx="26" ry="22"/><ellipse cx="178" cy="118" rx="26" ry="22"/><rect x="60" y="250" width="180" height="60"/></g>`;
      pattern = `<clipPath id="${id}k">${bodyClip}</clipPath>` + pattern;
    }
    const feet = t === 'oiseau' ? '' : `<ellipse cx="112" cy="${t === 'hamster' ? 272 : 276}" rx="24" ry="13" fill="${a.motif === 'masque' && !plush ? C2 : C}" stroke="${SH}" stroke-width="2"/><ellipse cx="188" cy="${t === 'hamster' ? 272 : 276}" rx="24" ry="13" fill="${a.motif === 'masque' && !plush ? C2 : C}" stroke="${SH}" stroke-width="2"/>`;

    // accessoires
    let acc = '';
    const neckY = t === 'hamster' ? 0 : 186;
    if (plush) {
      extra += `<path d="M150,${t === 'hamster' ? 190 : 200} L150,272" stroke="${SH}" stroke-width="2.5" stroke-dasharray="5 6" fill="none"/>`;
      const ac = pick(O.couleur_accessoire, a.couleur_accessoire).c;
      if (a.accessoire === 'noeud' && neckY) acc = `<path d="M150,188 L118,172 L118,204 Z M150,188 L182,172 L182,204 Z" fill="${ac}"/><circle cx="150" cy="188" r="9" fill="${shade(ac, -.15)}"/>`;
      if (a.accessoire === 'echarpe' && neckY) acc = `<path d="M100,178 Q150,200 200,178 L198,194 Q150,214 102,194 Z" fill="${ac}"/><path d="M170,196 L182,244 L164,242 Z" fill="${ac}"/>`;
    } else if (a.collier && a.collier !== 'aucun' && t !== 'oiseau') {
      const cc = pick(O.collier, a.collier).c, y = t === 'hamster' ? 232 : 186;
      acc = `<path d="M104,${y - 4} Q150,${y + 14} 196,${y - 4}" stroke="${cc}" stroke-width="9" fill="none" stroke-linecap="round"/><circle cx="150" cy="${y + 12}" r="7" fill="#F2C94C"/>`;
    }
    return `<svg viewBox="0 0 300 300" xmlns="http://www.w3.org/2000/svg">${behind}${tail}${ears}${bodyShape}${head}${pattern}${extra}${feet}${cheeks}${face}${acc}</svg>`;
  }

  /* ---------------- RECOLORATION INSTANTANÉE DES AVATARS PEINTS ----------------
     Masques pré-calculés (build_masks.py) : R, G, B = 3 zones. On change teinte, saturation et luminosité
     de chaque zone en gardant la texture peinte et la lumière (pas de filtre global). */
  let MST = null;
  const imgs = new Map(), outs = new Map();
  const loadImg = src => new Promise((ok, ko) => { const i = new Image(); i.onload = () => ok(i); i.onerror = ko; i.src = src; });
  async function pixels(name) {
    if (imgs.has(name)) return imgs.get(name);
    const p = (async () => {
      if (!MST) MST = await (await fetch('/static/avatars/masks.json?v=6')).json();
      const st = MST[name] || {};
      const [a, m, e, sh] = await Promise.all([loadImg(`/static/avatars/${name}.webp`), loadImg(`/static/avatars/${name}.mask.png?v=6`),
        st.eyes ? loadImg(`/static/avatars/${name}.eyes.png?v=6`).catch(() => null) : null,
        st.tenue ? loadImg(`/static/avatars/${name}.shirt.png?v=6`).catch(() => null) : null]);
      const c = document.createElement('canvas'); c.width = a.width; c.height = a.height;
      const x = c.getContext('2d', { willReadFrequently: true });
      const grab = im => { x.clearRect(0, 0, a.width, a.height); x.drawImage(im, 0, 0, a.width, a.height); return x.getImageData(0, 0, a.width, a.height).data.slice(); };
      const mask = grab(m), eyes = e ? grab(e) : null, shirt = sh ? grab(sh) : null;
      x.clearRect(0, 0, a.width, a.height); x.drawImage(a, 0, 0); const base = x.getImageData(0, 0, a.width, a.height);
      return { w: a.width, h: a.height, mask, eyes, shirt, base };
    })();
    imgs.set(name, p); return p;
  }
  function rgb2hsl(r, g, b) {
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2; let h = 0, s = 0;
    if (mx !== mn) {
      const d = mx - mn; s = d / Math.max(1e-6, 1 - Math.abs(2 * l - 1));
      h = mx === r ? ((g - b) / d + 6) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; h /= 6;
    }
    return [h, Math.min(1, s), l];
  }
  function hsl2rgb(h, s, l) {
    const c = (1 - Math.abs(2 * l - 1)) * s, hp = ((h % 1) + 1) % 1 * 6, x = c * (1 - Math.abs(hp % 2 - 1)), m = l - c / 2, i = Math.floor(hp) % 6;
    const t = [[c, x, 0], [x, c, 0], [0, c, x], [0, x, c], [x, 0, c], [c, 0, x]][i];
    return [t[0] + m, t[1] + m, t[2] + m];
  }
  const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255);
  /* même calcul que avatar_paint.py (serveur) : l'aperçu est exactement la base du livre */
  const lightMap = (l, lb, lt) => lt <= lb ? l * lt / Math.max(lb, 1e-3) : Math.min(0.96, Math.max(0, Math.min(lt, 0.72) + (l - lb) * 0.8));
  function zoneOf(base, target) {
    const [hb, sb, lb] = rgb2hsl(...base.map(v => v / 255)), [ht, stt, lt] = rgb2hsl(...hex(target));
    const ks = stt / Math.max(sb, .05);
    return { dh: ht - hb, ks: lt > lb ? Math.min(1, ks) : ks, lb, lt };
  }
  const WHITE = '#F4F0E6';
  function tenueAt(kind, X, Y, g, k, main, white) {     // couleur du vêtement en (X, Y) et détail peint (-1 sombre, +1 clair)
    const nx = g.neck[0] * k, ny = g.neck[1] * k, hw = g.hw * k, y0 = g.box[1] * k, y1 = g.box[3] * k;
    if (kind === 'mariniere') { const band = (y1 - y0) / 9.5; return [(((Y - y0) / band) % 2 + 2) % 2 < 1 ? white : main, 0]; }
    if (kind === 'salopette') {
      const top = ny + 38 * k, bx = hw + 30 * k;
      for (const sx of [-1, 1]) if ((X - (nx + sx * bx)) ** 2 + (Y - top - 2 * k) ** 2 < (6 * k) ** 2) return [main, 1];
      if ((Math.abs(Math.abs(X - nx) - bx) < 12 * k && Y < top + 4 * k) || (Math.abs(X - nx) < 62 * k && Y >= top)) return [main, 0];
      return [white, 0];
    }
    if (kind === 'sweat') {
      const d = Math.hypot((X - nx) / (hw + 14 * k), (Y - ny + 18 * k) / (46 * k));
      if (d > 0.8 && d < 1.08 && Y < ny + 30 * k) return [main, -1];
      for (const sx of [-1, 1]) if (Math.abs(X - (nx + sx * 13 * k)) < 2.6 * k && Y > ny + 4 * k && Y < ny + 52 * k) return [main, 1];
      return [main, 0];
    }
    if (kind === 'robe') {
      for (const sx of [-1, 1]) { const cx = nx + sx * hw * 0.78, cy = ny - 2 * k; if (((X - cx) / (hw * 1.2)) ** 2 + ((Y - cy) / (30 * k)) ** 2 < 1) return [white, 0]; }
      return [main, 0];
    }
    return [main, 0];
  }
  async function recolor(name, targets) {
    const key = name + JSON.stringify(targets);
    if (outs.has(key)) return outs.get(key);
    const job = (async () => {
      const P = await pixels(name), st = MST[name] || {}, d = new ImageData(new Uint8ClampedArray(P.base.data), P.w, P.h), px = d.data, M = P.mask;
      const zR = targets.R && st.R ? zoneOf(st.R, targets.R) : null, zG = targets.G && st.G ? zoneOf(st.G, targets.G) : null;
      const zE = targets.E && P.eyes ? rgb2hsl(...hex(targets.E)) : null;
      const kind = targets.tenue || 'pyjama', plain = kind !== 'pyjama' && P.shirt && st.tenue;
      const zB = !plain && targets.B && st.B ? zoneOf(st.B, targets.B) : null;
      const k = P.w / 480, main = rgb2hsl(...hex(targets.B || '#E9B840')), white = rgb2hsl(...hex(WHITE));
      for (let p = 0; p < px.length; p += 4) {
        if (!px[p + 3]) continue;
        let r = px[p] / 255, g = px[p + 1] / 255, b = px[p + 2] / 255;
        const mix = (w, c) => { r = r * (1 - w) + c[0] * w; g = g * (1 - w) + c[1] * w; b = b * (1 - w) + c[2] * w; };
        for (const [z, i] of [[zR, 0], [zG, 1]]) {
          const w = M[p + i] / 255; if (!z || w < .01) continue;
          const [h, s, l] = rgb2hsl(r, g, b);
          mix(w, hsl2rgb(h + z.dh, Math.min(1, s * z.ks), lightMap(l, z.lb, z.lt)));
        }
        if (zE) { const w = P.eyes[p] / 255; if (w > .01) { const [, , l] = rgb2hsl(r, g, b);
          mix(w, hsl2rgb(zE[0], Math.min(1, zE[1] * 1.2) * Math.min(1, Math.max(0, (l - 0.06) / 0.22)), lightMap(l, 0.33, Math.min(zE[2], .55)))); } }
        const wB = M[p + 2] / 255;
        if (wB > .01) {
          if (plain) {
            const n = p / 4, X = n % P.w, Y = (n - X) / P.w, lum = P.shirt[p] / 255;
            const [c, ex] = tenueAt(kind, X, Y, st.tenue, k, main, white);
            let l = lightMap(lum, st.tenue.lum, c[2]);
            if (ex > 0) l = Math.min(0.95, l * 0.25 + 0.72); else if (ex < 0) l *= 0.78;
            mix(wB, hsl2rgb(c[0], c[1], Math.max(0, Math.min(1, l))));
          } else if (zB) {
            const [h, s, l] = rgb2hsl(r, g, b);
            mix(wB, hsl2rgb(h + zB.dh, Math.min(1, s * zB.ks), lightMap(l, zB.lb, zB.lt)));
          }
        }
        px[p] = r * 255; px[p + 1] = g * 255; px[p + 2] = b * 255;
      }
      const c = document.createElement('canvas'); c.width = P.w; c.height = P.h; const x = c.getContext('2d'); x.putImageData(d, 0, 0);
      const E = st.eyes;
      if (E && (targets.freckles || targets.glasses)) overlays(x, E, targets);
      return c.toDataURL('image/png');
    })();
    outs.set(key, job); return job;
  }

  function overlays(x, E, t) {
    const [[x1, y1], [x2, y2]] = E, d = Math.hypot(x2 - x1, y2 - y1), ang = Math.atan2(y2 - y1, x2 - x1);
    let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    if (t.freckles) {                      // taches de rousseur : pommettes et arête du nez
      x.save(); x.translate((x1 + x2) / 2, (y1 + y2) / 2); x.rotate(ang);
      x.fillStyle = t.freckles;
      const spots = [[-d * .5, d * .55], [d * .5, d * .55], [0, d * .36]];
      spots.forEach(([cx, cy], k) => {
        for (let i = 0; i < (k === 2 ? 5 : 9); i++) {
          const px = cx + (rnd() - .5) * d * (k === 2 ? .32 : .42), py = cy + (rnd() - .5) * d * .22, r = d * (.018 + rnd() * .016);
          x.globalAlpha = .38 + rnd() * .3; x.beginPath(); x.arc(px, py, r, 0, 7); x.fill();
        }
      });
      x.restore();
    }
    if (t.glasses) {                       // lunettes peintes : ombre, monture, reflet
      const r = d * .43, col = t.glasses.color, round = t.glasses.type === 'rondes';
      const lens = (dx) => { x.beginPath(); if (round) x.arc(dx, 0, r, 0, 7); else x.roundRect(dx - r * 1.08, -r * .78, r * 2.16, r * 1.56, r * .38); };
      const frame = (stroke, lw, oy) => {
        x.save(); x.translate(0, oy); x.strokeStyle = stroke; x.lineWidth = lw; x.lineCap = 'round';
        lens(-d / 2); x.stroke(); lens(d / 2); x.stroke();
        x.beginPath(); x.moveTo(-d / 2 + r * (round ? .98 : 1.08), -r * .12); x.quadraticCurveTo(0, -r * .5, d / 2 - r * (round ? .98 : 1.08), -r * .12); x.stroke();
        x.beginPath(); x.moveTo(-d / 2 - r * (round ? 1 : 1.08), -r * .2); x.lineTo(-d / 2 - r * 1.75, -r * .42); x.stroke();
        x.beginPath(); x.moveTo(d / 2 + r * (round ? 1 : 1.08), -r * .2); x.lineTo(d / 2 + r * 1.75, -r * .42); x.stroke();
        x.restore();
      };
      x.save(); x.translate((x1 + x2) / 2, (y1 + y2) / 2 + d * .02); x.rotate(ang);
      x.fillStyle = 'rgba(255,255,255,.13)'; lens(-d / 2); x.fill(); lens(d / 2); x.fill();
      x.save(); x.filter = 'blur(2px)'; frame('rgba(40,20,10,.35)', r * .2, r * .08); x.restore();
      frame(col, r * .16, 0);
      frame(shade(col, .45), r * .05, -r * .045);
      x.strokeStyle = 'rgba(255,255,255,.55)'; x.lineWidth = r * .07; x.lineCap = 'round';
      [-d / 2, d / 2].forEach(cx => { x.beginPath(); x.arc(cx, 0, r * .62, Math.PI * 1.1, Math.PI * 1.35); x.stroke(); });
      x.restore();
    }
  }

  g.Avatar = { init: o => { OPT = o; }, child, creature, pick, recolor, shade };
})(window);
