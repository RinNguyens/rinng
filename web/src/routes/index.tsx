import { useEffect } from "react"
import { createFileRoute } from "@tanstack/react-router"
import { Landing } from "@/components/landing/landing"

// The rinng home page: the landing (components/landing). The app itself lives at /terminal.

const KIT = "/assets"
const TITLE = "rinng: open-source quant analysis for crypto perpetuals"
const DESCRIPTION =
  "rinng reads every USDT perpetual on Binance and OKX through market structure, Smart Money Concepts, liquidity, volume profile, order flow and Wyckoff, on your own machine, from public data."

export const Route = createFileRoute("/")({
  component: Page,
  head: () => ({
    meta: [
      { title: TITLE },
      { name: "description", content: DESCRIPTION },
      { name: "page-type", content: "software" },
      { name: "site-kind", content: "software" },
      { name: "theme-color", content: "#fcfcfc" },
      { property: "og:type", content: "website" },
      { property: "og:title", content: TITLE },
      { property: "og:description", content: DESCRIPTION },
      { property: "og:image", content: "/logo512.png" },
      { name: "twitter:card", content: "summary" },
    ],
    links: [
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap",
      },
      { rel: "stylesheet", href: `${KIT}/motion/motion.css` },
    ],
  }),
})

/** The kit's motion layer and page attributes, mounted once React has drawn the page (the app
 *  renders routes client-side only). StrictMode runs the effect twice; the teardown waits a tick so
 *  the second run cancels it. */
// The kit's motion layer loads once per visit to the site: a module run twice would register
// its document listeners twice. The page's own attributes come and go with the page, and the
// app's dark theme (set on <html> by the root) is put back when the page unmounts.
let motionLoaded = false
let restoreDark: boolean | null = null
let teardown: ReturnType<typeof setTimeout> | undefined
const ATTRS: Record<string, string> = { lang: "en", "data-type": "software", "data-motion": "", "data-page": "home" }

function Page() {
  useEffect(() => {
    clearTimeout(teardown)
    const html = document.documentElement
    // read the theme once, before this page changes it (StrictMode mounts the page twice)
    if (restoreDark === null) restoreDark = html.classList.contains("dark")
    html.classList.remove("dark")
    Object.entries(ATTRS).forEach(([k, v]) => html.setAttribute(k, v))
    if (!motionLoaded) {
      motionLoaded = true
      html.classList.add("m-enter", "mo-js")
      setTimeout(() => html.classList.add("m-enter-done"), 700)
      const el = document.createElement("script")
      el.type = "module"
      el.src = `${KIT}/motion/motion.js`
      document.body.append(el)
    }
    return () => {
      teardown = setTimeout(() => {
        html.classList.remove("m-enter", "m-enter-done", "mo-js")
        Object.keys(ATTRS).forEach((k) => k !== "lang" && html.removeAttribute(k))
        if (restoreDark) html.classList.add("dark")
        restoreDark = null
      }, 0)
    }
  }, [])
  return <Landing />
}
