import Link from "next/link";

export default function Page() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-50 text-slate-900">
      {/* Top bar */}
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-slate-800 to-slate-900 shadow-lg">
            <span className="text-lg font-bold text-white">S</span>
          </div>
          <span className="text-lg font-bold tracking-tight bg-gradient-to-r from-slate-800 to-slate-600 bg-clip-text text-transparent">
            SMARTACUS
          </span>
        </div>
        <nav className="hidden sm:flex items-center gap-6 text-sm font-medium">
          <a href="#how" className="text-slate-600 hover:text-slate-900 transition-colors">
            Fonctionnement
          </a>
          <a href="#pricing" className="text-slate-600 hover:text-slate-900 transition-colors">
            Tarifs
          </a>
          <a href="#pilot" className="text-slate-600 hover:text-slate-900 transition-colors">
            Pilote
          </a>
          <Link
            href="#cta"
            className="rounded-full bg-slate-900 px-5 py-2.5 text-white shadow-lg shadow-slate-900/25 hover:bg-slate-800 hover:shadow-xl transition-all"
          >
            Rejoindre
          </Link>
        </nav>
      </header>

      {/* Hero */}
      <section className="mx-auto w-full max-w-6xl px-6 pb-16 pt-12 sm:pt-20">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-amber-100 px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-amber-800 mb-6">
              <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse"></span>
              Anti-hype by design
            </div>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold leading-[1.1] tracking-tight">
              Décider{" "}
              <span className="bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                lucidement
              </span>{" "}
              avant de lancer.
            </h1>
            <p className="mt-6 text-lg leading-relaxed text-slate-600 max-w-xl">
              Smartacus n&apos;est pas un outil qui &quot;trouve des produits gagnants&quot;. C&apos;est un
              système qui{" "}
              <span className="font-semibold text-slate-900 underline decoration-blue-500 decoration-2 underline-offset-4">
                réduit les erreurs de décision
              </span>{" "}
              avant qu&apos;elles ne coûtent cher.
            </p>

            <div className="mt-8 flex flex-col sm:flex-row gap-4">
              <Link
                href="#cta"
                className="inline-flex items-center justify-center gap-2 rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 px-8 py-4 text-base font-semibold text-white shadow-lg shadow-blue-600/30 hover:shadow-xl hover:shadow-blue-600/40 hover:-translate-y-0.5 transition-all"
              >
                Rejoindre la phase pilote
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </Link>
              <a
                href="#how"
                className="inline-flex items-center justify-center gap-2 rounded-full border-2 border-slate-200 bg-white px-8 py-4 text-base font-semibold text-slate-900 hover:border-slate-300 hover:bg-slate-50 transition-all"
              >
                Voir comment ça marche
              </a>
            </div>
          </div>

          {/* Hero visual */}
          <div className="relative hidden lg:block">
            <div className="absolute inset-0 bg-gradient-to-r from-blue-500/10 to-indigo-500/10 rounded-3xl blur-3xl"></div>
            <div className="relative bg-white rounded-2xl shadow-2xl border border-slate-200 p-6 space-y-4">
              <div className="flex items-center gap-3 pb-4 border-b border-slate-100">
                <div className="h-3 w-3 rounded-full bg-red-400"></div>
                <div className="h-3 w-3 rounded-full bg-amber-400"></div>
                <div className="h-3 w-3 rounded-full bg-emerald-400"></div>
                <span className="ml-2 text-xs text-slate-400 font-mono">smartacus.app</span>
              </div>
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-emerald-400 to-emerald-500 flex items-center justify-center text-white font-bold shadow-lg">
                    72
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-slate-900">Support téléphone voiture</div>
                    <div className="text-xs text-slate-500">Lamicall — Score économique</div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <span className="px-2 py-1 rounded-md bg-emerald-100 text-emerald-700 text-xs font-medium">Marge forte</span>
                  <span className="px-2 py-1 rounded-md bg-blue-100 text-blue-700 text-xs font-medium">Gap produit</span>
                  <span className="px-2 py-1 rounded-md bg-amber-100 text-amber-700 text-xs font-medium">Fenêtre ouverte</span>
                </div>
                <div className="mt-4 p-3 rounded-xl bg-slate-50 border border-slate-100">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-lg">🟢</span>
                    <span className="font-medium text-slate-900">État : Éclairé</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-600">Données solides, risques connus, action recommandée.</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Feature pills */}
        <div className="mt-16 grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { icon: "🎯", label: "Détecte quand une opportunité existe" },
            { icon: "💡", label: "Explique pourquoi elle existe" },
            { icon: "⚠️", label: "Affiche ce qui manque avant d'agir" },
            { icon: "📋", label: "Trace les décisions (Risk Journal)" },
          ].map((item, i) => (
            <div
              key={i}
              className="flex items-center gap-3 rounded-2xl bg-white border border-slate-200 px-5 py-4 shadow-sm hover:shadow-md hover:border-slate-300 transition-all"
            >
              <span className="text-2xl">{item.icon}</span>
              <span className="text-sm font-medium text-slate-700">{item.label}</span>
            </div>
          ))}
        </div>
      </section>

      {/* What it is / isn't */}
      <section className="mx-auto w-full max-w-6xl px-6 py-16">
        <div className="grid md:grid-cols-2 gap-8">
          <div className="rounded-3xl bg-gradient-to-br from-red-50 to-orange-50 border border-red-100 p-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-red-100 flex items-center justify-center">
                <svg className="w-5 h-5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <h2 className="text-xl font-bold text-slate-900">Ce que Smartacus ne fait pas</h2>
            </div>
            <ul className="space-y-4">
              {[
                "Pas de promesse de \"winner\"",
                "Pas de \"fonce\" déguisé en score",
                "Pas d'angles morts cachés",
                "Pas de ROI garanti",
              ].map((item, i) => (
                <li key={i} className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-red-200 flex items-center justify-center mt-0.5">
                    <span className="w-2 h-2 rounded-full bg-red-500"></span>
                  </span>
                  <span className="text-slate-700">{item}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-3xl bg-gradient-to-br from-emerald-50 to-teal-50 border border-emerald-100 p-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-emerald-100 flex items-center justify-center">
                <svg className="w-5 h-5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h2 className="text-xl font-bold text-slate-900">Ce que Smartacus fait vraiment</h2>
            </div>
            <ul className="space-y-4">
              {[
                "Analyse marché : signal → thèse → risques",
                "Confiance affichée : 🟢 / 🟡 / 🔴",
                "Actions \"réduire l'incertitude\" (pas GO par défaut)",
                "Journal de risque + boucle post-mortem",
              ].map((item, i) => (
                <li key={i} className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-emerald-200 flex items-center justify-center mt-0.5">
                    <svg className="w-3 h-3 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  </span>
                  <span className="text-slate-700">{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* Confidence */}
      <section className="mx-auto w-full max-w-6xl px-6 py-16" id="how">
        <div className="text-center mb-12">
          <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">
            Une IA qui sait dire{" "}
            <span className="bg-gradient-to-r from-violet-600 to-purple-600 bg-clip-text text-transparent">
              &quot;je ne sais pas&quot;
            </span>
          </h2>
          <p className="mt-4 text-lg text-slate-600 max-w-2xl mx-auto">
            Chaque opportunité affiche ce que le système sait, ce qu&apos;il ne sait pas, et ce qu&apos;il faut faire pour réduire l&apos;incertitude.
          </p>
        </div>

        <div className="grid sm:grid-cols-3 gap-6">
          <div className="group rounded-2xl bg-gradient-to-br from-emerald-500 to-emerald-600 p-1 shadow-xl shadow-emerald-500/20 hover:shadow-2xl hover:shadow-emerald-500/30 transition-all">
            <div className="h-full rounded-xl bg-white p-6">
              <div className="w-14 h-14 rounded-2xl bg-emerald-100 flex items-center justify-center text-3xl mb-4">
                🟢
              </div>
              <h3 className="text-lg font-bold text-slate-900">Éclairé</h3>
              <p className="mt-2 text-slate-600">
                Données solides, risques connus, action claire. Feu vert pour avancer.
              </p>
            </div>
          </div>

          <div className="group rounded-2xl bg-gradient-to-br from-amber-400 to-amber-500 p-1 shadow-xl shadow-amber-400/20 hover:shadow-2xl hover:shadow-amber-400/30 transition-all">
            <div className="h-full rounded-xl bg-white p-6">
              <div className="w-14 h-14 rounded-2xl bg-amber-100 flex items-center justify-center text-3xl mb-4">
                🟡
              </div>
              <h3 className="text-lg font-bold text-slate-900">Incomplet</h3>
              <p className="mt-2 text-slate-600">
                Potentiel réel, mais zones floues. Action principale : réduire l&apos;incertitude.
              </p>
            </div>
          </div>

          <div className="group rounded-2xl bg-gradient-to-br from-red-500 to-red-600 p-1 shadow-xl shadow-red-500/20 hover:shadow-2xl hover:shadow-red-500/30 transition-all">
            <div className="h-full rounded-xl bg-white p-6">
              <div className="w-14 h-14 rounded-2xl bg-red-100 flex items-center justify-center text-3xl mb-4">
                🔴
              </div>
              <h3 className="text-lg font-bold text-slate-900">Fragile</h3>
              <p className="mt-2 text-slate-600">
                Décision possible, mais risquée. Override possible, jamais silencieux.
              </p>
            </div>
          </div>
        </div>

        <div className="mt-10 rounded-2xl bg-gradient-to-r from-slate-800 to-slate-900 p-8 text-white">
          <div className="flex flex-col sm:flex-row sm:items-center gap-6">
            <div className="flex-shrink-0 w-16 h-16 rounded-2xl bg-white/10 backdrop-blur flex items-center justify-center">
              <svg className="w-8 h-8 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div>
              <h3 className="text-xl font-bold">Risk Override</h3>
              <p className="mt-2 text-slate-300">
                Si tu avances malgré 🟡/🔴, tu dois expliciter ton hypothèse (amélioration produit, marketing, test...).
                La décision est tracée, et un retour est demandé après 14 jours (post-mortem).
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Product diagnostic */}
      <section className="mx-auto w-full max-w-6xl px-6 py-16">
        <div className="text-center mb-12">
          <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">
            Diagnostic produit{" "}
            <span className="bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent">
              actionnable
            </span>
          </h2>
        </div>

        <div className="grid md:grid-cols-2 gap-8">
          <div className="rounded-3xl bg-white border border-slate-200 p-8 shadow-lg hover:shadow-xl transition-shadow">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-2xl text-white mb-6 shadow-lg shadow-violet-500/30">
              📊
            </div>
            <h3 className="text-xl font-bold text-slate-900">Review Intelligence</h3>
            <p className="mt-3 text-slate-600">
              Extraction automatique des défauts dominants, regroupement des demandes clients (&quot;I wish...&quot;) et calcul du score d&apos;amélioration.
            </p>
            <ul className="mt-6 space-y-3">
              {[
                "Défauts récurrents (sévérité × fréquence)",
                "Features manquantes (wishes normalisés)",
                "Improvement score (actionnable)",
              ].map((item, i) => (
                <li key={i} className="flex items-center gap-3 text-sm text-slate-700">
                  <span className="w-1.5 h-1.5 rounded-full bg-violet-500"></span>
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-3xl bg-white border border-slate-200 p-8 shadow-lg hover:shadow-xl transition-shadow">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center text-2xl text-white mb-6 shadow-lg shadow-blue-500/30">
              📋
            </div>
            <h3 className="text-xl font-bold text-slate-900">Spec OEM + RFQ + QC</h3>
            <p className="mt-3 text-slate-600">
              Génération d&apos;une spec produit utilisable : corrections prioritaires, features, checklist qualité, et message RFQ.
            </p>
            <ul className="mt-6 space-y-3">
              {[
                "Bloc A : corrections (priorisées)",
                "Bloc B : différenciation (features)",
                "QC checklist (mandatory / recommended)",
                "Export RFQ (copier/coller)",
              ].map((item, i) => (
                <li key={i} className="flex items-center gap-3 text-sm text-slate-700">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="mx-auto w-full max-w-6xl px-6 py-16" id="pricing">
        <div className="text-center mb-12">
          <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">
            Prix simple,{" "}
            <span className="bg-gradient-to-r from-emerald-500 to-teal-500 bg-clip-text text-transparent">
              sans piège
            </span>
          </h2>
          <p className="mt-4 text-lg text-slate-600">
            Pas de commission, pas de &quot;success fee&quot;, pas de promesse de ROI.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto">
          <div className="relative rounded-3xl bg-white border-2 border-slate-200 p-8 shadow-lg">
            <div className="absolute -top-4 left-8 px-4 py-1 rounded-full bg-slate-900 text-white text-xs font-semibold">
              ABONNEMENT
            </div>
            <div className="mt-4 flex items-baseline gap-2">
              <span className="text-5xl font-bold text-slate-900">49€</span>
              <span className="text-lg text-slate-500">/ mois</span>
            </div>
            <ul className="mt-8 space-y-4">
              {[
                "Accès dashboard & shortlist",
                "Scans planifiés (budget contrôlé)",
                "Agents IA (réponses structurées)",
                "Historique & audit",
                "Risk Journal + post-mortem",
              ].map((item, i) => (
                <li key={i} className="flex items-center gap-3">
                  <svg className="w-5 h-5 text-emerald-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span className="text-slate-700">{item}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-3xl bg-gradient-to-br from-slate-50 to-slate-100 border border-slate-200 p-8">
            <div className="text-sm font-semibold text-slate-900 uppercase tracking-wider">Usage</div>
            <p className="mt-4 text-slate-600">
              Facturé uniquement quand tu déclenches une action qui génère un livrable.
            </p>
            <ul className="mt-6 space-y-3">
              {[
                "Spec OEM générée",
                "Export RFQ fournisseur",
                "Checklist QC usine",
              ].map((item, i) => (
                <li key={i} className="flex items-center gap-3">
                  <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                  <span className="text-slate-700">{item}</span>
                </li>
              ))}
            </ul>
            <p className="mt-6 text-xs text-slate-500 bg-white/60 rounded-lg px-3 py-2">
              Tarification usage à préciser pendant la phase pilote.
            </p>
          </div>
        </div>
      </section>

      {/* Pilot */}
      <section className="mx-auto w-full max-w-6xl px-6 py-16" id="pilot">
        <div className="rounded-3xl bg-gradient-to-br from-indigo-600 via-violet-600 to-purple-700 p-10 text-white shadow-2xl">
          <div className="flex items-start gap-4 mb-8">
            <div className="w-12 h-12 rounded-2xl bg-white/20 backdrop-blur flex items-center justify-center flex-shrink-0">
              <span className="text-2xl">🇫🇷</span>
            </div>
            <div>
              <h2 className="text-2xl sm:text-3xl font-bold">Phase pilote — France</h2>
              <p className="mt-2 text-indigo-100 max-w-xl">
                Nous cherchons des vendeurs Amazon (déjà actifs) qui préfèrent comprendre les risques plutôt que suivre un score.
                Ce n&apos;est pas pour tout le monde — volontairement.
              </p>
            </div>
          </div>

          <div className="grid sm:grid-cols-3 gap-6">
            {[
              { icon: "👤", title: "Profil", desc: "1+ produits lancés, logique business." },
              { icon: "💬", title: "Attendu", desc: "Feedback court et honnête." },
              { icon: "📅", title: "Durée", desc: "30 jours, itérations minimales." },
            ].map((item, i) => (
              <div key={i} className="rounded-2xl bg-white/10 backdrop-blur-sm p-5">
                <div className="text-2xl mb-3">{item.icon}</div>
                <div className="font-semibold">{item.title}</div>
                <div className="mt-1 text-sm text-indigo-100">{item.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto w-full max-w-6xl px-6 py-20" id="cta">
        <div className="text-center">
          <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">
            Prêt à{" "}
            <span className="bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
              décider lucidement
            </span>{" "}
            ?
          </h2>
          <p className="mt-4 text-lg text-slate-600 max-w-xl mx-auto">
            Accès limité. Pas de promesse de ROI. Un outil pour décider — et assumer ses décisions.
          </p>

          <div className="mt-10 flex flex-col sm:flex-row justify-center gap-4">
            <Link
              href="/dashboard"
              className="inline-flex items-center justify-center gap-2 rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 px-10 py-4 text-lg font-semibold text-white shadow-lg shadow-blue-600/30 hover:shadow-xl hover:shadow-blue-600/40 hover:-translate-y-0.5 transition-all"
            >
              Accéder au dashboard
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </Link>
            <a
              href="mailto:pilot@smartacus.app?subject=Acc%C3%A8s%20pilote%20Smartacus%20(FR)"
              className="inline-flex items-center justify-center gap-2 rounded-full border-2 border-slate-200 bg-white px-10 py-4 text-lg font-semibold text-slate-900 hover:border-slate-300 hover:bg-slate-50 transition-all"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              Écrire un email
            </a>
          </div>

          <p className="mt-10 text-slate-500 italic">
            &quot;Smartacus ne te dira jamais quoi faire. Il t&apos;aidera à comprendre ce que tu fais.&quot;
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="mx-auto w-full max-w-6xl px-6 pb-10">
        <div className="flex flex-col sm:flex-row justify-between items-center gap-4 border-t border-slate-200 pt-8">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900">
              <span className="text-sm font-bold text-white">S</span>
            </div>
            <span className="text-sm text-slate-500">
              Smartacus © {new Date().getFullYear()} — Sonde économique Amazon
            </span>
          </div>
          <div className="flex gap-6 text-sm text-slate-500">
            <a href="#how" className="hover:text-slate-900 transition-colors">
              Fonctionnement
            </a>
            <a href="#pricing" className="hover:text-slate-900 transition-colors">
              Tarifs
            </a>
            <a href="#pilot" className="hover:text-slate-900 transition-colors">
              Pilote
            </a>
          </div>
        </div>
      </footer>
    </main>
  );
}
