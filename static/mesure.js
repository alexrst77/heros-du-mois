/* Mesure d'audience et des conversions, avec consentement (CNIL).
   Rien n'est chargé tant que la personne n'a pas accepté, et rien du tout si aucun outil n'est réglé dans Railway
   (variables GA4_ID, META_PIXEL_ID, GOOGLE_ADS_ID + GOOGLE_ADS_ACHAT). Événements : voir window.mesure(…). */
(function () {
  const CLE = 'mhm-consentement';
  let cfg = null, actif = false, file = [], pret = false;
  const lire = () => { try { return localStorage.getItem(CLE); } catch (_) { return null; } };
  const ecrire = v => { try { localStorage.setItem(CLE, v); } catch (_) {} };
  const script = src => { const s = document.createElement('script'); s.async = true; s.src = src; document.head.appendChild(s); };

  function charger() {
    if (actif || !cfg) return; actif = true;
    if (cfg.ga4 || cfg.gads) {
      script('https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(cfg.ga4 || cfg.gads));
      window.dataLayer = window.dataLayer || []; window.gtag = function () { dataLayer.push(arguments); };
      gtag('js', new Date());
      if (cfg.ga4) gtag('config', cfg.ga4, { anonymize_ip: true });
      if (cfg.gads) gtag('config', cfg.gads);
    }
    if (cfg.meta) {
      !function (f, b, e, v, n, t, s) { if (f.fbq) return; n = f.fbq = function () { n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments); };
        if (!f._fbq) f._fbq = n; n.push = n; n.loaded = !0; n.version = '2.0'; n.queue = []; t = b.createElement(e); t.async = !0; t.src = v;
        s = b.getElementsByTagName(e)[0]; s.parentNode.insertBefore(t, s); }(window, document, 'script', 'https://connect.facebook.net/en_US/fbevents.js');
      fbq('init', cfg.meta); fbq('track', 'PageView');
    }
    file.forEach(([n, p]) => envoyer(n, p)); file = [];
  }
  const META = { voir_produit: 'ViewContent', creation_commencee: 'CustomizeProduct', ajout_produit: 'AddToCart', paiement_commence: 'InitiateCheckout', achat: 'Purchase' };
  const GA = { voir_produit: 'view_item', ajout_produit: 'add_to_cart', paiement_commence: 'begin_checkout', achat: 'purchase' };
  function envoyer(nom, p) {
    p = p || {};
    if (window.gtag && cfg.ga4) gtag('event', GA[nom] || nom, Object.assign({ currency: 'EUR' }, p));
    if (window.fbq && cfg.meta) fbq(META[nom] ? 'track' : 'trackCustom', META[nom] || nom, p.value != null ? { value: p.value, currency: 'EUR' } : {});
    if (nom === 'achat' && window.gtag && cfg.gads && cfg.gads_achat) gtag('event', 'conversion', { send_to: cfg.gads + '/' + cfg.gads_achat, value: p.value, currency: 'EUR', transaction_id: p.transaction_id });
  }
  /* window.mesure('achat', { value: 149.4, transaction_id: 'abc' }) — mis en attente tant que le choix n'est pas fait */
  window.mesure = function (nom, p) { if (!pret) { file.push([nom, p]); return; } if (!cfg || lire() === 'non') return; if (actif) envoyer(nom, p); else file.push([nom, p]); };

  function bandeau() {
    if (document.getElementById('mhm-cookies')) return;
    const d = document.createElement('div'); d.id = 'mhm-cookies'; d.setAttribute('role', 'dialog'); d.setAttribute('aria-label', 'Cookies');
    d.innerHTML = '<p>Nous aimerions mesurer quelles publicités vous ont amené ici, pour en faire moins et mieux. Rien n\'est activé sans votre accord. <a href="/confidentialite">En savoir plus</a></p>' +
      '<div><button type="button" data-c="non">Refuser</button><button type="button" data-c="oui">Accepter</button></div>';
    d.style.cssText = 'position:fixed;left:16px;right:16px;bottom:16px;z-index:99;max-width:560px;margin:0 auto;background:#1F2557;color:#fff;border-radius:16px;padding:14px 16px;box-shadow:0 18px 40px rgba(0,0,0,.3);font:500 14px/1.45 Nunito,system-ui,sans-serif;display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center';
    d.querySelector('p').style.cssText = 'margin:0;flex:1 1 280px'; d.querySelector('a').style.color = '#FFC94A';
    d.querySelectorAll('button').forEach(b => { b.style.cssText = 'border:0;border-radius:999px;padding:9px 16px;font:800 14px Nunito,system-ui,sans-serif;cursor:pointer;margin-left:6px;' + (b.dataset.c === 'oui' ? 'background:#FFC94A;color:#1F2557' : 'background:transparent;color:#fff;border:1.5px solid rgba(255,255,255,.5)');
      b.onclick = () => { ecrire(b.dataset.c); d.remove(); if (b.dataset.c === 'oui') charger(); else file = []; }; });
    document.body.appendChild(d);
  }
  window.mesureChoix = () => { if (cfg) bandeau(); else alert("Aucun outil de mesure n'est activé sur ce site."); };

  fetch('/api/mesure').then(r => r.json()).then(c => {
    pret = true;
    if (!c || !(c.ga4 || c.meta || c.gads)) { cfg = null; file = []; return; }
    cfg = c;
    const choix = lire();
    if (choix === 'oui') charger(); else if (choix !== 'non') bandeau();
  }).catch(() => { pret = true; file = []; });
})();
