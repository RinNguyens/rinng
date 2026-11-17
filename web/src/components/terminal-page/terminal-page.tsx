import { ExchangeIcon, TokenIcon } from "@web3icons/react/dynamic"
import { Candles } from "./charts"
import type { Overlay } from "./charts"
import "./terminal-page.css"

/* type: software (site-kind software): the rinng terminal, a self-hosted chart terminal for crypto
   USDT perpetuals, built with the design-taste-frontend kit (public/assets).
   deal: hero collage, nav nav-cards, close close-word, footer footer-columns, rhythm surface-pairs,
     buttons tonal, mark: the client's own logo (stack dealt, not used), ground sand,
     palette white-mint-tiles (white ground, mint accent: the colour of an up candle on a chart
     terminal), type mona (Mona Sans + Geist Mono), radius sharp (a trading tool).
   moments: line-carries-colour on #combos (the surface band)
   effect: none dealt onto the page; grounds: the lit sand ground behind the hero's window only.
   plan (1440x900):
     hero       chart terminal for crypto perpetual traders; the watchlist window + a bar-close card   1  ui
     workspace  chart tabs in eight layouts, crosshairs in sync; app-frame: tab list + 2x2 charts    1  object (app-frame)
     lenses     four of the seven lenses, each drawn on a chart (features-2x2)                         1  ui fragments
     combos     seven combos, each answers one question; split, the combo's reading guide (moment)  1  ui
     start      runs on your machine: the steps beside the live command                              1  ui (terminal)
     questions  orders, keys, exchanges, cost, systems, data (faq)                                   1  none
     closing    close-word + footer-columns                                                          1
   voice: technical-dry; "you" for the trader, the terminal is the subject of feature lines. */

const GITHUB = "https://github.com/RinNguyens/rinng"
const APP = "/app"
const MAIN = "Open the terminal"

const Arrow = () => (
  <svg className="m-arrow" viewBox="0 0 12 12" aria-hidden="true">
    <path className="m-arrow__stem" d="M1 6h8" />
    <path className="m-arrow__head" d="M4.5 2.5 8 6l-3.5 3.5" />
  </svg>
)

const Chev = () => (
  <svg className="chev" viewBox="0 0 12 12" aria-hidden="true">
    <path d="M3 4.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

const Coin = ({ symbol }: { symbol: string }) => (
  <span className="d-thumb tp-coin">
    <TokenIcon symbol={symbol} variant="branded" size={24} aria-hidden />
  </span>
)

const Venue = ({ id }: { id: "binance" | "okx" }) => (
  <ExchangeIcon id={id} variant="branded" size={14} aria-hidden className="tp-venue" />
)

const WATCH = [
  { sym: "btc", id: "BTC-USDT-PERP", venue: "binance" as const, px: "96,412.5", chip: ["", "Bar closed"] },
  { sym: "eth", id: "ETH-USDT-PERP", venue: "binance" as const, px: "3,318.20", chip: ["", "Live"] },
  { sym: "sol", id: "SOL-USDT-PERP", venue: "okx" as const, px: "187.34", chip: ["d-chip--low", "Sweep"] },
  { sym: "bnb", id: "BNB-USDT-PERP", venue: "binance" as const, px: "702.10", chip: ["", "Live"] },
  { sym: "link", id: "LINK-USDT-PERP", venue: "okx" as const, px: "21.886", chip: ["d-chip--out", "CHoCH"] },
  { sym: "xrp", id: "XRP-USDT-PERP", venue: "binance" as const, px: "2.3141", chip: ["", "Live"] },
]

const TABS = [
  { name: "Dashboard", sub: "Market read, desk and news", lay: "—" },
  { name: "Top-down structure", sub: "1 large + 2 · 1d, 4h, 1h", lay: "1+2" },
  { name: "Value vs. liquidity", sub: "2 columns · 4h, 4h", lay: "2" },
  { name: "Trend health", sub: "1 large + 2 · 4h", lay: "1+2" },
  { name: "Positioning & squeeze risk", sub: "1 large + 2 · 1h", lay: "1+2" },
  { name: "Market cycle", sub: "1 large + 2 · 1d, 4h", lay: "1+2" },
  { name: "Risk map", sub: "1 large + 2 · 4h", lay: "1+2" },
  { name: "Intraday plan", sub: "2×2 · 1h, 15m", lay: "2×2" },
  { name: "BTC scalp", sub: "3 columns · 15m", lay: "3" },
  { name: "Alts on 4h", sub: "3×2 · 4h", lay: "3×2" },
]

const LENS_CARDS: Array<{ title: string; text: string; overlay: Overlay; seed: number; label: string }> = [
  { title: "Marks order blocks and breaks", text: "Order blocks, fair value gaps and each BOS or CHoCH, drawn where they happened.", overlay: "structure", seed: 11, label: "ETH 4h · SMC structure" },
  { title: "Draws liquidity lines on the chart", text: "Equal highs and lows become BSL and SSL lines: where the stops rest.", overlay: "liquidity", seed: 23, label: "SOL 1h · Liquidity" },
  { title: "Adds a volume profile to each chart", text: "Point of control and value area for the range, per day or per week.", overlay: "profile", seed: 5, label: "BTC 4h · Volume profile" },
  { title: "Projects a price cone on the chart", text: "80% and 90% bands for the coming bars, with the odds of touching each level.", overlay: "cone", seed: 31, label: "BTC 4h · Projection" },
]

const FAQ = [
  { q: "Does the terminal place orders?", a: "No. rinng only reads market data, and nothing it shows is investment advice." },
  { q: "Do I need exchange API keys?", a: "No. Every chart comes from public Binance and OKX data: klines, funding and open interest." },
  { q: "Which markets does the terminal cover?", a: "USDT perpetuals on Binance and OKX. Any listed coin opens from the search." },
  { q: "What does the terminal cost?", a: "Nothing. rinng is open source under the MIT licence." },
  { q: "Where does the terminal keep data?", a: "On your disk, as Parquet files queried with DuckDB." },
]

export function TerminalPage() {
  return (
    <>
      <header className="nav">
        <div className="wrap nav__bar">
          <a className="skip-link" href="#top">
            Skip to content
          </a>
          <a className="nav__logo" href="#top">
            <img src="/logo.svg" alt="" width="28" height="28" className="tp-logo" />
            rinng
          </a>
          <nav className="nav__links" aria-label="Main">
            <div className="nav__item">
              <a className="nav__link" href="#workspace">
                Workspace <Chev />
              </a>
              <div className="nav__menu">
                <div className="wrap grid">
                  {[
                    { href: "#workspace", t: "Chart tabs", s: "Eight layouts, one crosshair across them", o: "structure" as Overlay, seed: 3 },
                    { href: "#lenses", t: "Analysis lenses", s: "Seven reads drawn on the price", o: "liquidity" as Overlay, seed: 19 },
                    { href: "#combos", t: "Chart combos", s: "Ready tabs that answer one question", o: "profile" as Overlay, seed: 8 },
                  ].map((m) => (
                    <a key={m.t} className="menu-card span-4" href={m.href}>
                      <div className="panel tp-menu-panel">
                        <Candles seed={m.seed} overlay={m.o} bars={32} width={400} height={200} />
                      </div>
                      <span className="t-card">{m.t}</span>
                      <span className="t-small muted">{m.s}</span>
                    </a>
                  ))}
                </div>
              </div>
            </div>
            <div className="nav__item">
              <a className="nav__link" href="#lenses">
                Lenses
              </a>
            </div>
            <div className="nav__item">
              <a className="nav__link" href="#combos">
                Combos
              </a>
            </div>
            <div className="nav__item">
              <a className="nav__link" href="#start">
                Setup
              </a>
            </div>
            <div className="nav__item">
              <a className="nav__link" href="#questions">
                Questions
              </a>
            </div>
          </nav>
          <div className="nav__actions">
            <a className="nav__link" href={GITHUB}>
              GitHub
            </a>
            <a className="btn btn--primary" href={APP}>
              {MAIN}
            </a>
          </div>
          <button className="nav__toggle" type="button" aria-expanded="false" aria-label="Menu">
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <path d="M2 5h14M2 13h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        </div>
      </header>

      <main id="top">
        <section className="hero hero--collage" data-enter aria-labelledby="hero-h">
          <div className="wrap">
            <div className="hero-text grid hero__grid">
              <div className="hero__text span-5">
                <h1 id="hero-h">Chart terminal for crypto perpetual traders</h1>
                <p className="hero__lead">
                  Every USDT perpetual on Binance and OKX in multi-chart tabs, with 7 analysis lenses drawn on the price. Free and
                  open source, on macOS or Linux.
                </p>
                <div className="btn-row">
                  <a className="btn btn--primary" href={APP}>
                    {MAIN}
                    <Arrow />
                  </a>
                  <a className="btn btn--secondary" href="#start">
                    Read the setup steps
                  </a>
                </div>
                <p className="hero__proof">Public market data only: no API keys, no orders.</p>
              </div>
              <div className="hero__art span-6 start-7" role="img" aria-label="The rinng watchlist with six perpetuals, and a card reporting a closed 4h bar on BTC">
                <div className="ly-piece ly-piece--main d-win" aria-hidden="true">
                  <div className="d-win__bar">
                    <span className="d-win__dots">
                      <i></i>
                      <i></i>
                      <i></i>
                    </span>
                    <span>rinng · Dashboard</span>
                  </div>
                  <div className="d-win__body">
                    <div className="d-side">
                      <span className="is-on">
                        <i></i>Dashboard
                      </span>
                      <span>
                        <i></i>Chart tabs
                      </span>
                      <span>
                        <i></i>Library
                      </span>
                      <span>
                        <i></i>Desk
                      </span>
                      <span>
                        <i></i>News
                      </span>
                      <span className="d-side__label">Exchanges</span>
                      <span>
                        <Venue id="binance" />
                        Binance
                      </span>
                      <span>
                        <Venue id="okx" />
                        OKX
                      </span>
                    </div>
                    <div className="d-main">
                      <div className="d-main__head">
                        <h4>Watchlist</h4>
                        <span className="d-btn">Add chart tab</span>
                      </div>
                      <div className="d-tabs">
                        <span className="is-on">All</span>
                        <span>Binance</span>
                        <span>OKX</span>
                      </div>
                      <div className="d-rows">
                        {WATCH.map((w) => (
                          <div className="d-row tp-row" key={w.id}>
                            <Coin symbol={w.sym} />
                            <div>
                              <b>{w.id}</b>
                              <small>
                                {w.venue === "okx" ? "OKX" : "Binance"} perpetual
                              </small>
                            </div>
                            <span className="num">{w.px}</span>
                            <span className={`d-chip ${w.chip[0]}`}>{w.chip[1]}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
                <div className="ly-piece ly-piece--note d-card" aria-hidden="true" data-ly-steps="700">
                  <div className="d-card__row">
                    <h5>BTC 4h bar closed</h5>
                    <span className="d-chip" data-step data-step-at="4">
                      Read
                    </span>
                  </div>
                  <div className="d-note__line" data-step>
                    <i className="warn">!</i>
                    <span>
                      Swept the high at <b>96,980</b>
                    </span>
                  </div>
                  <div className="d-note__line" data-step>
                    <i>✓</i>
                    <span>
                      Bullish order block <b>95,140</b>
                    </span>
                  </div>
                  <div className="d-note__line" data-step>
                    <i>✓</i>
                    <span>
                      Cone redrawn for <b>12 bars</b>
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="section" id="workspace">
          <div className="wrap">
            <div className="grid">
              <h2 className="span-5">
                Chart tabs in eight layouts. <span className="muted">Crosshairs move together.</span>
              </h2>
              <p className="span-6 start-7 t-lead tp-intro">
                Keep a tab per idea: one coin across timeframes, or four coins side by side. Each chart picks its own lens.{" "}
                <a className="link" href="#combos">
                  See the seven combos
                </a>
              </p>
            </div>
            <div className="ui app fill" role="img" aria-label="The chart tabs list beside an open Intraday plan tab: four BTC charts in a 2×2 layout">
              <div className="app__pane app__pane--list">
                <div className="d-win tp-list">
                  <div className="d-win__bar">
                    <span className="d-win__dots">
                      <i></i>
                      <i></i>
                      <i></i>
                    </span>
                    <span>Chart tabs</span>
                  </div>
                  <div className="d-rows tp-tabs">
                    {TABS.map((t) => (
                      <div className={`tp-tab${t.name === "Intraday plan" ? " is-sel" : ""}`} key={t.name}>
                        <div>
                          <b>{t.name}</b>
                          <small>{t.sub}</small>
                        </div>
                        <span className="tp-lay">{t.lay}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              <div className="app__pane app__pane--open">
                <div className="tp-grid">
                  <Candles seed={41} overlay="profile" bars={40} label="BTC 1h · Daily profile" />
                  <Candles seed={41} overlay="liquidity" bars={40} label="BTC 15m · Liquidity" />
                  <Candles seed={9} overlay="none" bars={40} label="BTC 15m · Indicators" />
                  <Candles seed={41} overlay="cone" bars={40} label="BTC 1h · Projection" />
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="section" id="lenses" style={{ "--hm": 2 } as React.CSSProperties}>
          <div className="wrap">
            <div className="section-head">
              <h2>
                Seven lenses for one chart. <span className="muted">Each reads the same bars.</span>
              </h2>
            </div>
            <div className="grid tp-lenses">
              {LENS_CARDS.map((c) => (
                <article className="card card--open card--row span-6" key={c.title}>
                  <h3 className="t-card">{c.title}</h3>
                  <p>{c.text}</p>
                  <div className="panel">
                    <div className="stage stage--fade-b tp-stage">
                      <Candles seed={c.seed} overlay={c.overlay} bars={44} width={620} height={240} label={c.label} />
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="section ground-surface" id="combos" data-moment="line-carries-colour" data-moment-opts='{"from": "base"}'>
          <div className="wrap">
            <div className="grid">
              <div className="span-5 tp-split-text">
                <h2>Seven combos, each built for one question</h2>
                <p className="t-lead">
                  A combo opens a ready tab: the layout, the timeframe and the lens on every chart, plus the order to read them in.
                </p>
                <ul className="tp-facts">
                  <li>Top-down structure: which way is the higher-timeframe trend?</li>
                  <li>Risk map: how far can price travel this week?</li>
                  <li>Positioning: are longs or shorts crowded?</li>
                </ul>
                <a className="link" href="#workspace">
                  See how the tabs work
                </a>
              </div>
              <div className="frame frame--split span-6 start-7">
                <div className="stage stage--fade-br">
                  <div className="d-win tp-guide">
                    <div className="d-win__bar">
                      <span className="d-win__dots">
                        <i></i>
                        <i></i>
                        <i></i>
                      </span>
                      <span>Positioning &amp; squeeze risk</span>
                    </div>
                    <div className="d-main">
                      <div className="d-main__head">
                        <h4>Are longs or shorts crowded, and where would a squeeze run to?</h4>
                      </div>
                      <ol className="tp-steps">
                        <li>
                          <b>Derivatives</b> High funding, rising open interest and a skewed long-short ratio mark the crowded side.
                        </li>
                        <li>
                          <b>Liquidity</b> The crowded side&rsquo;s stops sit past the nearest BSL or SSL: a squeeze ends there.
                        </li>
                        <li>
                          <b>Daily profile</b> P and b days, with delta, show who pushed during the build-up.
                        </li>
                      </ol>
                      <div className="tp-mini">
                        <Candles seed={63} overlay="liquidity" bars={40} width={560} height={260} label="BTC 1h · Liquidity" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="section" id="start">
          <div className="wrap">
            <div className="section-head">
              <h2>
                Runs on your machine in six commands. <span className="muted">Python 3.12 and Node 22.</span>
              </h2>
            </div>
            <div className="grid tp-start">
              <ol className="span-5 tp-steps tp-steps--page">
                <li>
                  <b>Install</b> uv sync sets up Python and every dependency.
                </li>
                <li>
                  <b>Backfill</b> Downloads history from Binance dumps and both exchange APIs.
                </li>
                <li>
                  <b>Analyse</b> Writes features and events for each timeframe, 15m to 1w.
                </li>
                <li>
                  <b>Go live</b> Starts the collector and serves the terminal on port 8000.
                </li>
              </ol>
              <div className="span-6 start-7 tp-term-wrap">
                <div className="ui ui-panel ui-term tp-term" aria-label="A terminal running the rinng setup commands" role="img">
                  <div className="ui-term__head">
                    <span className="ui-dots" aria-hidden="true">
                      <i></i>
                      <i></i>
                      <i></i>
                    </span>
                    <span className="ui-term__title">~/rinng</span>
                    <span className="ui-meta">zsh</span>
                  </div>
                  <pre className="tp-code" aria-hidden="true">
                    <span className="tp-c"># install Python 3.12 and dependencies</span>
                    {"\n"}
                    <span className="tp-p">$</span> uv sync{"\n"}
                    <span className="tp-c"># download history into data/</span>
                    {"\n"}
                    <span className="tp-p">$</span> uv run rinng backfill --start 2024-01-01{"\n"}
                    <span className="tp-p">$</span> uv run rinng resample{"\n"}
                    <span className="tp-p">$</span> uv run rinng analyze --timeframe 4h{"\n"}
                    <span className="tp-p">$</span> pnpm --dir web install &amp;&amp; pnpm --dir web build{"\n"}
                    <span className="tp-p">$</span> uv run rinng live{"\n"}
                    <span className="tp-o">rinng live: http://127.0.0.1:8000</span>
                  </pre>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="section" id="questions">
          <div className="wrap">
            <div className="grid">
              <div className="span-5 tp-split-text">
                <h2>Questions about the terminal</h2>
                <p className="t-lead">Anything else goes to the issue tracker, where the code lives.</p>
                <a className="link" href={`${GITHUB}/issues`}>
                  Ask on GitHub
                </a>
                <ul className="tp-sources" aria-label="Data sources">
                  <li>
                    <ExchangeIcon id="binance" variant="branded" size={32} aria-hidden />
                    Binance USDT perpetuals
                  </li>
                  <li>
                    <ExchangeIcon id="okx" variant="branded" size={32} aria-hidden />
                    OKX USDT perpetuals
                  </li>
                </ul>
              </div>
              <div className="faq span-6 start-7">
                {FAQ.map((f) => (
                  <div className="faq__item" key={f.q}>
                    <h3>{f.q}</h3>
                    <p>{f.a}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="closing" id="contact">
        <div className="wrap">
          <div className="closing__cta close--word">
            <div className="section-head--split">
              <div>
                <h2 id="close-h">Open the terminal on your own data</h2>
                <p className="t-lead">MIT licence, on macOS or Linux, reading only public market data.</p>
              </div>
              <a className="btn btn--primary" href={APP}>
                {MAIN}
                <Arrow />
              </a>
            </div>
            <p className="close__word" aria-hidden="true">
              rinng
            </p>
          </div>
          <div className="closing__links">
            <div className="grid">
              <div className="span-4 stack-4">
                <a className="nav__logo" href="#top">
                  <img src="/logo.svg" alt="" width="28" height="28" className="tp-logo" />
                  rinng
                </a>
                <p className="footer__lede">A chart terminal for crypto perpetuals.</p>
              </div>
              <div className="span-2 footer__col">
                <h3>Workspace</h3>
                <ul>
                  <li>
                    <a href="#workspace">Chart tabs</a>
                  </li>
                  <li>
                    <a href="#lenses">Lenses</a>
                  </li>
                </ul>
              </div>
              <div className="span-2 footer__col">
                <h3>Combos</h3>
                <ul>
                  <li>
                    <a href="#combos">Chart combos</a>
                  </li>
                  <li>
                    <a href="/">rinng home</a>
                  </li>
                </ul>
              </div>
              <div className="span-2 footer__col">
                <h3>Setup</h3>
                <ul>
                  <li>
                    <a href="#start">Setup steps</a>
                  </li>
                  <li>
                    <a href={GITHUB}>Source code</a>
                  </li>
                </ul>
              </div>
              <div className="span-2 footer__col">
                <h3>Questions</h3>
                <ul>
                  <li>
                    <a href="#questions">Questions</a>
                  </li>
                  <li>
                    <a href={`${GITHUB}/issues`}>Issues</a>
                  </li>
                </ul>
              </div>
            </div>
            <div className="footer__legal">
              <span>&copy; 2026 rinng, MIT licence</span>
              <div className="socials"></div>
              <span>Product names and logos are trademarks of their owners</span>
            </div>
          </div>
        </div>
      </footer>
    </>
  )
}
