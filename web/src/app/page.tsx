import Link from "next/link";

/* ──────────────────────── Icons ──────────────────────── */

const ArrowRight = () => (
  <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
  </svg>
);

const CheckCircle = () => (
  <svg className="h-5 w-5 text-emerald-500 shrink-0" fill="currentColor" viewBox="0 0 20 20">
    <path
      fillRule="evenodd"
      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
      clipRule="evenodd"
    />
  </svg>
);

const ScanIcon = () => (
  <svg className="h-7 w-7" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
  </svg>
);

const ReviewIcon = () => (
  <svg className="h-7 w-7" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
  </svg>
);

const SpecIcon = () => (
  <svg className="h-7 w-7" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
  </svg>
);

const AgentIcon = () => (
  <svg className="h-7 w-7" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
  </svg>
);

/* ──────────────────────── Page ──────────────────────── */

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white">
      {/* ─── Navbar ─── */}
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-white/80 backdrop-blur-lg">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-primary-700 text-sm font-bold text-white shadow-md shadow-primary-200">
              S
            </div>
            <span className="text-lg font-bold text-gray-900">Smartacus</span>
          </Link>

          <nav className="hidden items-center gap-8 md:flex">
            <a href="#features" className="text-sm font-medium text-gray-500 transition hover:text-gray-900">Fonctionnalites</a>
            <a href="#how" className="text-sm font-medium text-gray-500 transition hover:text-gray-900">Comment ca marche</a>
            <a href="#pricing" className="text-sm font-medium text-gray-500 transition hover:text-gray-900">Tarifs</a>
            <a href="#faq" className="text-sm font-medium text-gray-500 transition hover:text-gray-900">FAQ</a>
          </nav>

          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-xl bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white shadow-md shadow-primary-200 transition hover:bg-primary-700 hover:shadow-lg hover:shadow-primary-200"
          >
            Essayer maintenant <ArrowRight />
          </Link>
        </div>
      </header>

      {/* ─── Hero ─── */}
      <section className="relative overflow-hidden">
        {/* Background gradient */}
        <div className="absolute inset-0 -z-10 bg-gradient-to-b from-primary-50/60 via-white to-white" />
        <div className="absolute -top-40 right-0 -z-10 h-[500px] w-[500px] rounded-full bg-primary-100/40 blur-3xl" />
        <div className="absolute -bottom-20 -left-20 -z-10 h-[400px] w-[400px] rounded-full bg-primary-50/60 blur-3xl" />

        <div className="mx-auto max-w-7xl px-6 pb-20 pt-20 md:pt-28">
          <div className="mx-auto max-w-3xl text-center">
            {/* Badge */}
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-primary-200 bg-primary-50 px-4 py-1.5 text-sm font-medium text-primary-700">
              <span className="h-2 w-2 rounded-full bg-primary-500 animate-pulse" />
              Sonde economique Amazon &mdash; Pilote France
            </div>

            <h1 className="text-4xl font-extrabold leading-tight tracking-tight text-gray-900 sm:text-5xl md:text-6xl">
              Trouve quoi lancer.
              <br />
              <span className="bg-gradient-to-r from-primary-600 to-primary-400 bg-clip-text text-transparent">
                Bats le produit en place.
              </span>
            </h1>

            <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-gray-500">
              Smartacus scanne le marche Amazon, identifie les fenetres d&apos;opportunite,
              analyse les avis clients, et genere une <strong className="text-gray-700">spec OEM + checklist QC + message RFQ</strong> prets
              a envoyer a ton fournisseur.
            </p>

            <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
              <Link
                href="/dashboard"
                className="inline-flex items-center gap-2 rounded-xl bg-primary-600 px-7 py-3.5 text-base font-semibold text-white shadow-lg shadow-primary-200 transition hover:bg-primary-700 hover:shadow-xl hover:shadow-primary-300"
              >
                Essayer maintenant <ArrowRight />
              </Link>
              <a
                href="#how"
                className="inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-7 py-3.5 text-base font-semibold text-gray-700 shadow-sm transition hover:bg-gray-50 hover:border-gray-300"
              >
                Comprendre en 60s
              </a>
            </div>

            {/* Trust markers */}
            <div className="mt-10 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-gray-400">
              <span className="flex items-center gap-1.5">
                <CheckCircle /> Scoring 100% deterministe
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle /> Shortlist contrainte (5 max)
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle /> Review Intelligence integree
              </span>
            </div>
          </div>

          {/* Hero visual — mock dashboard card */}
          <div className="mx-auto mt-16 max-w-4xl">
            <div className="rounded-2xl border border-gray-200 bg-white p-1 shadow-2xl shadow-gray-200/50">
              <div className="rounded-xl bg-gradient-to-br from-gray-50 to-gray-100 p-6 md:p-8">
                <div className="grid gap-4 md:grid-cols-3">
                  {/* Score card */}
                  <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                    <div className="text-xs font-medium uppercase tracking-wider text-gray-400">Score Opportunite</div>
                    <div className="mt-2 text-4xl font-extrabold text-primary-600">82<span className="text-lg text-gray-400">/100</span></div>
                    <div className="mt-3 grid grid-cols-5 gap-1">
                      <div className="h-1.5 rounded-full bg-primary-500" />
                      <div className="h-1.5 rounded-full bg-primary-400" />
                      <div className="h-1.5 rounded-full bg-primary-300" />
                      <div className="h-1.5 rounded-full bg-primary-200" />
                      <div className="h-1.5 rounded-full bg-gray-100" />
                    </div>
                    <div className="mt-3 text-xs text-gray-500">Marge 42% &bull; Velocity +35% &bull; Gap fort</div>
                  </div>

                  {/* Review Intelligence card */}
                  <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                    <div className="text-xs font-medium uppercase tracking-wider text-gray-400">Review Intelligence</div>
                    <div className="mt-3 space-y-2.5">
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">Pain dominant</span>
                        <span className="rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-semibold text-red-600">poor_grip</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">Top wish</span>
                        <span className="rounded-full bg-primary-50 px-2.5 py-0.5 text-xs font-semibold text-primary-600">wireless charging</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">Improvement</span>
                        <span className="text-sm font-bold text-emerald-600">68%</span>
                      </div>
                    </div>
                  </div>

                  {/* Deliverables card */}
                  <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                    <div className="text-xs font-medium uppercase tracking-wider text-gray-400">Livrables generes</div>
                    <div className="mt-3 space-y-2.5">
                      <div className="flex items-center gap-2.5">
                        <CheckCircle />
                        <span className="text-sm text-gray-700">Spec OEM (10 exigences)</span>
                      </div>
                      <div className="flex items-center gap-2.5">
                        <CheckCircle />
                        <span className="text-sm text-gray-700">Checklist QC (11 tests)</span>
                      </div>
                      <div className="flex items-center gap-2.5">
                        <CheckCircle />
                        <span className="text-sm text-gray-700">Message RFQ pret</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Features ─── */}
      <section id="features" className="border-t border-gray-100 bg-gray-50/50 py-20 md:py-28">
        <div className="mx-auto max-w-7xl px-6">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight text-gray-900 md:text-4xl">
              Un systeme qui <span className="text-primary-600">decide</span>, pas un dashboard de plus
            </h2>
            <p className="mt-4 text-lg text-gray-500">
              Smartacus remplace la recherche produit manuelle par un workflow executable :
              detection, diagnostic, spec, RFQ.
            </p>
          </div>

          <div className="mt-16 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {[
              {
                icon: <ScanIcon />,
                title: "Scan & Shortlist",
                desc: "Scan automatique de niche, shortlist contrainte (5 max) classee par valeur x urgence. Zero interpretation manuelle.",
                bg: "bg-primary-50",
              },
              {
                icon: <ReviewIcon />,
                title: "Review Intelligence",
                desc: "Extraction des defauts dominants, des wishes clients et d'un improvement score pour concevoir un meilleur produit.",
                bg: "bg-emerald-50",
              },
              {
                icon: <SpecIcon />,
                title: "Spec OEM + QC + RFQ",
                desc: "Generation automatique de la spec fournisseur, checklist QC et message RFQ. Pret a copier-coller.",
                bg: "bg-violet-50",
              },
              {
                icon: <AgentIcon />,
                title: "Agents IA",
                desc: "4 agents specialises (Discovery, Analyst, Sourcing, Negotiator) avec contexte data-driven, pas des chatbots generiques.",
                bg: "bg-amber-50",
              },
            ].map((f, i) => (
              <div key={i} className="group rounded-2xl border border-gray-200 bg-white p-6 shadow-sm transition hover:shadow-md hover:border-gray-300">
                <div className={`inline-flex rounded-xl ${f.bg} p-3 text-gray-700`}>
                  {f.icon}
                </div>
                <h3 className="mt-4 text-lg font-semibold text-gray-900">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-gray-500">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── How it works ─── */}
      <section id="how" className="py-20 md:py-28">
        <div className="mx-auto max-w-7xl px-6">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight text-gray-900 md:text-4xl">
              Comment ca marche
            </h2>
            <p className="mt-4 text-lg text-gray-500">
              De la detection a l&apos;envoi au fournisseur, en 4 etapes.
            </p>
          </div>

          <div className="relative mt-16">
            {/* Connecting line */}
            <div className="absolute left-1/2 top-0 hidden h-full w-px -translate-x-1/2 bg-gradient-to-b from-primary-200 via-primary-300 to-primary-200 md:block" />

            <div className="grid gap-12 md:gap-0">
              {[
                {
                  step: "01",
                  title: "Scan de niche",
                  desc: "Smartacus interroge Keepa pour decouvrir les ASINs de la niche, collecte prix, BSR, stock, avis. 10 000 ASINs filtres en quelques secondes.",
                  align: "right" as const,
                },
                {
                  step: "02",
                  title: "Scoring & Shortlist",
                  desc: "Chaque ASIN recoit un score deterministe sur 100 (Margin/30, Velocity/25, Competition/20, Gap/15, TimePressure/10). Seuls les 5 meilleurs passent.",
                  align: "left" as const,
                },
                {
                  step: "03",
                  title: "Review Intelligence",
                  desc: "Extraction des defauts recurrents, des features demandees par les clients, et calcul du improvement score. Le brief produit se construit tout seul.",
                  align: "right" as const,
                },
                {
                  step: "04",
                  title: "Spec OEM + RFQ",
                  desc: "Generation de la spec fournisseur (Bloc A: corriger les defauts, Bloc B: ajouter les features), checklist QC, et message RFQ pret a envoyer.",
                  align: "left" as const,
                },
              ].map((item, i) => (
                <div key={i} className="relative md:py-8">
                  {/* Step number on the line */}
                  <div className="absolute left-1/2 top-1/2 z-10 hidden h-10 w-10 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-gradient-to-br from-primary-500 to-primary-600 text-sm font-bold text-white shadow-lg shadow-primary-200 md:flex">
                    {item.step}
                  </div>

                  <div className={`md:w-1/2 ${item.align === "right" ? "md:ml-auto md:pl-16" : "md:mr-auto md:pr-16"}`}>
                    <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
                      <div className="mb-3 flex items-center gap-3 md:hidden">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-600 text-xs font-bold text-white">{item.step}</div>
                      </div>
                      <h3 className="text-lg font-semibold text-gray-900">{item.title}</h3>
                      <p className="mt-2 text-sm leading-relaxed text-gray-500">{item.desc}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ─── Pricing ─── */}
      <section id="pricing" className="border-t border-gray-100 bg-gray-50/50 py-20 md:py-28">
        <div className="mx-auto max-w-7xl px-6">
          <div className="mx-auto max-w-2xl text-center">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-4 py-1.5 text-sm font-medium text-emerald-700">
              Pilote France &bull; Acces fondateur
            </div>
            <h2 className="text-3xl font-bold tracking-tight text-gray-900 md:text-4xl">
              Tarification simple et transparente
            </h2>
            <p className="mt-4 text-lg text-gray-500">
              Un abonnement pour surveiller. Des credits a l&apos;usage quand tu passes a l&apos;execution.
            </p>
          </div>

          <div className="mt-16 grid gap-8 md:grid-cols-2 lg:max-w-4xl lg:mx-auto">
            {/* Subscription card */}
            <div className="relative overflow-hidden rounded-2xl border-2 border-primary-200 bg-white p-8 shadow-lg shadow-primary-100/50">
              <div className="absolute right-0 top-0 rounded-bl-xl bg-primary-600 px-3 py-1 text-xs font-semibold text-white">Recommande</div>
              <div className="text-sm font-semibold uppercase tracking-wider text-primary-600">Abonnement</div>
              <div className="mt-2 flex items-baseline gap-1">
                <span className="text-5xl font-extrabold text-gray-900">49&euro;</span>
                <span className="text-lg text-gray-400">/mois</span>
              </div>
              <p className="mt-3 text-sm text-gray-500">Acces complet + scans automatises</p>

              <ul className="mt-8 space-y-3">
                {[
                  "Scans de niche (refresh 24-48h)",
                  "Shortlist contrainte (5 opportunites max)",
                  "These economique + action recommandee",
                  "Panneau Review Intelligence",
                  "Product Spec Panel (si specs dispo)",
                  "4 Agents IA (Discovery, Analyst, Sourcing, Negotiator)",
                ].map((f, i) => (
                  <li key={i} className="flex items-start gap-3 text-sm text-gray-700">
                    <CheckCircle />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>

              <Link
                href="/dashboard"
                className="mt-8 flex w-full items-center justify-center gap-2 rounded-xl bg-primary-600 py-3 text-sm font-semibold text-white shadow-md shadow-primary-200 transition hover:bg-primary-700"
              >
                Demarrer le pilote <ArrowRight />
              </Link>
            </div>

            {/* Usage card */}
            <div className="rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
              <div className="text-sm font-semibold uppercase tracking-wider text-gray-400">A l&apos;usage</div>
              <div className="mt-2 text-2xl font-bold text-gray-900">Paie quand tu executes</div>
              <p className="mt-3 text-sm text-gray-500">Livrables d&apos;execution factures a l&apos;unite</p>

              <div className="mt-8 space-y-4">
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-gray-900">Spec OEM generee</div>
                      <div className="mt-1 text-xs text-gray-500">Bloc A (fix defects) + Bloc B (features) + priorites</div>
                    </div>
                    <div className="text-2xl font-bold text-gray-900">15&euro;</div>
                  </div>
                </div>

                <div className="rounded-xl border border-gray-200 bg-gray-50 p-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-gray-900">Export RFQ + QC</div>
                      <div className="mt-1 text-xs text-gray-500">Message fournisseur + checklist QC exportable</div>
                    </div>
                    <div className="text-2xl font-bold text-gray-900">5&euro;</div>
                  </div>
                </div>
              </div>

              <div className="mt-6 rounded-xl bg-amber-50 border border-amber-100 p-4 text-sm text-amber-800">
                <strong>Optionnel.</strong> L&apos;abonnement suffit pour recevoir la shortlist.
                L&apos;usage sert quand tu veux passer a l&apos;execution.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── CTA ─── */}
      <section className="py-20 md:py-28">
        <div className="mx-auto max-w-7xl px-6">
          <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-primary-600 to-primary-800 px-8 py-16 text-center shadow-2xl shadow-primary-300/30 md:px-16">
            {/* Decorative circles */}
            <div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/10 blur-2xl" />
            <div className="absolute -bottom-10 -left-10 h-40 w-40 rounded-full bg-white/10 blur-2xl" />

            <h2 className="relative text-3xl font-bold text-white md:text-4xl">
              Pret a tester Smartacus ?
            </h2>
            <p className="relative mx-auto mt-4 max-w-xl text-lg text-primary-100">
              Accede a la shortlist en temps reel, explore les opportunites avec les agents IA,
              et genere tes premieres specs OEM.
            </p>
            <div className="relative mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
              <Link
                href="/dashboard"
                className="inline-flex items-center gap-2 rounded-xl bg-white px-8 py-3.5 text-base font-semibold text-primary-700 shadow-lg transition hover:bg-primary-50"
              >
                Essayer maintenant <ArrowRight />
              </Link>
              <a
                href="#how"
                className="inline-flex items-center gap-2 rounded-xl border border-white/30 px-8 py-3.5 text-base font-semibold text-white transition hover:bg-white/10"
              >
                Voir le flow
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* ─── FAQ ─── */}
      <section id="faq" className="border-t border-gray-100 bg-gray-50/50 py-20 md:py-28">
        <div className="mx-auto max-w-7xl px-6">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight text-gray-900 md:text-4xl">
              Questions frequentes
            </h2>
          </div>

          <div className="mx-auto mt-12 max-w-3xl divide-y divide-gray-200">
            {[
              {
                q: "Pourquoi un abonnement + usage ?",
                a: "L'abonnement finance la surveillance (scans, shortlist quotidienne). L'usage ne se declenche que quand tu veux des livrables d'execution (spec, RFQ, QC). Tu paies proportionnellement a l'action.",
              },
              {
                q: "Est-ce que je vois les KPIs detailles ?",
                a: "Oui, dans les panneaux de detail. Mais l'objectif est d'eviter l'overload : tu recois une shortlist courte avec une these economique et une action recommandee. Le detail (score breakdown, reviews, spec) est accessible si tu veux creuser.",
              },
              {
                q: "Les agents IA sont-ils generiques ?",
                a: "Non. Ils s'appuient sur les artefacts data reels : evenements economiques, composantes du score, review profile, spec bundle. Ils expliquent et proposent des actions data-driven specifiques au produit.",
              },
              {
                q: "Je peux commencer sans payer l'usage ?",
                a: "Oui. L'abonnement suffit pour recevoir la shortlist et utiliser les agents IA. L'usage sert uniquement quand tu veux generer des livrables d'execution (spec OEM, exports RFQ/QC).",
              },
              {
                q: "Comment fonctionne le scoring ?",
                a: "100% deterministe, pas de boite noire. 5 composantes : Margin (30pts), Velocity (25pts), Competition (20pts), Gap (15pts), TimePressure (10pts). Chaque composante est explicable dans le panneau de detail.",
              },
            ].map((item, i) => (
              <div key={i} className="py-6">
                <h3 className="text-base font-semibold text-gray-900">{item.q}</h3>
                <p className="mt-3 text-sm leading-relaxed text-gray-500">{item.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Footer ─── */}
      <footer className="border-t border-gray-200 bg-white py-10">
        <div className="mx-auto flex max-w-7xl flex-col items-center gap-4 px-6 md:flex-row md:justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary-500 to-primary-700 text-xs font-bold text-white">
              S
            </div>
            <span className="text-sm font-semibold text-gray-900">Smartacus</span>
            <span className="text-sm text-gray-400">&mdash; Sonde economique Amazon</span>
          </div>
          <div className="flex items-center gap-6 text-sm text-gray-400">
            <Link href="/dashboard" className="transition hover:text-gray-600">Dashboard</Link>
            <span>&copy; {new Date().getFullYear()}</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
