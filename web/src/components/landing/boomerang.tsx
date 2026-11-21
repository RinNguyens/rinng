import { useEffect, useRef, useState } from "react"

/* Boomerang video background: the clip plays once while every frame is captured to an offscreen
   canvas (requestVideoFrameCallback, else requestAnimationFrame; deduplicated by currentTime);
   on `ended` the video hides and a canvas plays the frames forward then backward at 30 fps,
   for ever. Capture width is capped at 960px and scaled to the screen so a phone keeps its memory.
   Long or 60 fps clips are capped at 30 frames a second and their first 8 seconds.
   Paused or under reduced motion it holds the current frame. */

const MAX_SECONDS = 8

type VideoWithRvfc = HTMLVideoElement & {
  requestVideoFrameCallback?: (cb: (now: number, meta: { mediaTime: number }) => void) => number
  cancelVideoFrameCallback?: (id: number) => void
}

export function BoomerangVideoBg({ src, running, reduced }: { src: string; running: boolean; reduced: boolean }) {
  const video = useRef<VideoWithRvfc>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const frames = useRef<Array<HTMLCanvasElement>>([])
  const [ready, setReady] = useState(false)
  const live = useRef({ running, reduced })
  live.current = { running, reduced }

  // capture while the clip plays once
  useEffect(() => {
    const v = video.current
    if (!v) return
    if (reduced) {
      v.pause()
      return
    }
    let stopped = false
    let handle = 0
    let lastTime = -1
    const captured: Array<HTMLCanvasElement> = []
    const capW = Math.min(960, Math.max(480, Math.round((v.parentElement?.clientWidth ?? 960) * 0.66)))

    const finish = () => {
      if (stopped) return
      v.pause()
      onEnded()
    }
    const grab = () => {
      if (stopped || !v.videoWidth) return
      if (v.currentTime === lastTime) return
      // at most 30 frames a second (a 60 fps clip keeps every other frame) and the first 8 s
      if (lastTime >= 0 && v.currentTime - lastTime < 1 / 31) return
      if (v.currentTime > MAX_SECONDS) return finish()
      lastTime = v.currentTime
      const w = capW
      const h = Math.round((v.videoHeight / v.videoWidth) * w)
      const c = document.createElement("canvas")
      c.width = w
      c.height = h
      c.getContext("2d")?.drawImage(v, 0, 0, w, h)
      captured.push(c)
    }
    const schedule = () => {
      if (stopped) return
      // Safari before 15.4 and some webviews lack it
      if ("requestVideoFrameCallback" in v) {
        handle = v.requestVideoFrameCallback(() => {
          grab()
          schedule()
        })
      } else {
        handle = requestAnimationFrame(() => {
          grab()
          schedule()
        })
      }
    }
    const onPlay = () => schedule()
    const onEnded = () => {
      stopped = true
      if (captured.length > 1) {
        frames.current = captured
        setReady(true)
      } else {
        v.loop = true // capture failed: fall back to a plain loop
        void v.play().catch(() => {})
      }
    }
    v.muted = true
    v.addEventListener("play", onPlay)
    v.addEventListener("ended", onEnded)
    void v.play().catch(() => {})
    return () => {
      stopped = true
      v.removeEventListener("play", onPlay)
      v.removeEventListener("ended", onEnded)
      if ("cancelVideoFrameCallback" in v) v.cancelVideoFrameCallback(handle)
      cancelAnimationFrame(handle)
    }
  }, [reduced])

  // ping-pong playback on the display canvas
  useEffect(() => {
    if (!ready) return
    const cv = canvas.current
    const list = frames.current
    if (!cv || list.length < 2) return
    cv.width = list[0].width
    cv.height = list[0].height
    const ctx = cv.getContext("2d")
    if (!ctx) return
    const interval = 1000 / 30
    let i = list.length - 1
    let dir = -1
    let last = 0
    let raf = 0
    ctx.drawImage(list[i], 0, 0)
    const tick = (now: number) => {
      raf = requestAnimationFrame(tick)
      const { running: run, reduced: red } = live.current
      if (!run || red || now - last < interval) return
      last = now
      i += dir
      if (i >= list.length - 1) {
        i = list.length - 1
        dir = -1
      } else if (i <= 0) {
        i = 0
        dir = 1
      }
      ctx.drawImage(list[i], 0, 0)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [ready])

  return (
    <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden" aria-hidden="true">
      <div className="h-full w-full origin-top scale-[1.15] overflow-hidden">
        <video
          ref={video}
          src={src}
          muted
          playsInline
          preload="auto"
          crossOrigin="anonymous"
          className="h-full w-full object-cover object-top"
          style={{ display: ready ? "none" : "block" }}
        />
        <canvas ref={canvas} className="h-full w-full object-cover object-top" style={{ display: ready ? "block" : "none" }} />
      </div>
    </div>
  )
}
