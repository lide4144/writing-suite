import { Link } from 'react-router-dom'

// 404（§8.4）：场景不存在 —— 「这个舞台不存在」，附返回场景画廊链接。
export function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-stage-950 px-6 text-center">
      <div className="text-5xl">🎭</div>
      <h1 className="mt-8 font-serif text-3xl text-stone-100">这个舞台不存在</h1>
      <p className="mt-4 max-w-md text-sm leading-relaxed text-stone-500">
        你找的剧目没有排期——或许它从未上演，或许早已落幕。
      </p>
      <Link
        to="/"
        className="mt-10 rounded-lg border border-gold/40 bg-gold/10 px-6 py-2.5 text-sm text-gold transition-colors hover:bg-gold/20"
      >
        ← 返回场景画廊
      </Link>
    </div>
  )
}
