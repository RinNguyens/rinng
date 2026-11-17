import { useEffect } from "react"
import { createFileRoute } from "@tanstack/react-router"
import { TerminalPage } from "@/components/terminal-page/terminal-page"

// The terminal's page: what the rinng chart terminal is and how to run it, built with the
// design-taste-frontend kit in public/assets. The terminal itself (the chart app) lives at /app.

const KIT = "/assets"
const TITLE = "rinng terminal: chart terminal for crypto perpetual traders"
const DESCRIPTION =
  "Multi-chart tabs for every USDT perpetual on Binance and OKX, with SMC, liquidity, volume profile and projection lenses, self-hosted and free."

export const Route = createFileRoute("/terminal")({
  component: Page,
  head: () => ({
    meta: [
      { title: TITLE },
      { name: "description", content: DESCRIPTION },
      { name: "page-type", content: "software" },
      { name: "site-kind", content: "software" },
      { name: "theme-color", content: "#ffffff" },
      { property: "og:type", content: "website" },
      { property: "og:title", content: TITLE },
      { property: "og:description", content: "The rinng chart terminal: multi-chart tabs and seven analysis lenses for crypto perpetuals." },
      { property: "og:image", content: "/logo512.png" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Mona+Sans:wdth,wght@75..125,400..600&family=Geist+Mono:wght@400..500&display=swap",
      },
      { rel: "stylesheet", href: `${KIT}/system.css` },
      { rel: "stylesheet", href: `${KIT}/ui/cards.css` },
      { rel: "stylesheet", href: `${KIT}/motion/motion.css` },
      { rel: "stylesheet", href: `${KIT}/backgrounds/backgrounds.css` },
      { rel: "stylesheet", href: `${KIT}/layout/layout.css` },
      { rel: "stylesheet", href: `${KIT}/icons/icon.css` },
      { rel: "stylesheet", href: `${KIT}/ui/base.css` },
      { rel: "stylesheet", href: `${KIT}/ui/terminal-run/fragment.css` },
    ],
  }),
})

// The kit's scripts are modules that wire up the page once; each loads once per visit.
const ATTRS: Record<string, string> = {
  lang: "en",
  "data-type": "software",
  "data-radius": "sharp",
  "data-ground": "sand",
  "data-buttons": "tonal",
  "data-motion": "",
  "data-page": "terminal",
}
const SCRIPTS = ["system.js", "motion/motion.js", "layout/layout.js"]
let restoreDark: boolean | null = null
let teardown: ReturnType<typeof setTimeout> | undefined

function load(src: string, module = true) {
  const url = `${KIT}/${src}`
  if (document.querySelector(`script[src="${url}"]`)) return
  const el = document.createElement("script")
  if (module) el.type = "module"
  el.src = url
  document.body.append(el)
}

function Page() {
  useEffect(() => {
    clearTimeout(teardown)
    const html = document.documentElement
    if (restoreDark === null) restoreDark = html.classList.contains("dark")
    html.classList.remove("dark")
    Object.entries(ATTRS).forEach(([k, v]) => html.setAttribute(k, v))
    html.classList.add("m-enter", "mo-js")
    setTimeout(() => html.classList.add("m-enter-done"), 700)
    setTimeout(() => html.classList.add("mo-safe"), 2500)
    load("backgrounds/backgrounds.js", false)
    SCRIPTS.forEach((s) => load(s))
    return () => {
      teardown = setTimeout(() => {
        html.classList.remove("m-enter", "m-enter-done", "mo-js", "mo-safe")
        Object.keys(ATTRS).forEach((k) => k !== "lang" && html.removeAttribute(k))
        if (restoreDark) html.classList.add("dark")
        restoreDark = null
      }, 0)
    }
  }, [])
  return <TerminalPage />
}
