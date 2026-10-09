import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Scene } from '../types'
import { createScene, getScenes } from '../mock/api'
import { SceneCard } from '../components/gallery/SceneCard'

// 场景画廊（§4）：剧院大厅。卡片网格 + 创建新场景 + 空状态引导。
export function GalleryPage() {
  const [scenes, setScenes] = useState<Scene[] | null>(null)
  const [creating, setCreating] = useState(false)
  const navigate = useNavigate()

  const refresh = () => {
    getScenes().then(setScenes)
  }

  useEffect(() => {
    let cancelled = false
    getScenes().then((list) => {
      if (!cancelled) setScenes(list)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const handleCreate = async () => {
    if (creating) return
    setCreating(true)
    try {
      const scene = await createScene()
      navigate(`/stage/${scene.id}/setup`)
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="min-h-screen bg-stage-950 px-10 pb-20 pt-16">
      <div className="mx-auto max-w-[1400px]">
        <header className="flex items-end justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-wide text-stone-100">舞台</h1>
            <p className="mt-2 text-sm text-stone-500">剧院大厅 · 选择一场戏，入座观看</p>
          </div>
          <button
            type="button"
            onClick={handleCreate}
            disabled={creating}
            className="rounded-lg border border-gold/40 bg-gold/10 px-5 py-2.5 text-sm font-medium text-gold transition-colors hover:bg-gold/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {creating ? '创建中…' : '＋ 创建新场景'}
          </button>
        </header>

        {scenes === null ? (
          // 加载中：骨架卡片
          <div className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        ) : scenes.length === 0 ? (
          // 空状态：引导创建第一个场景
          <div className="mt-28 flex flex-col items-center text-center">
            <div className="text-4xl">🎭</div>
            <p className="mt-6 font-serif text-lg text-stone-300">舞台还空着，幕布尚未拉开。</p>
            <p className="mt-2 text-sm text-stone-500">创建第一个场景，让角色们登场。</p>
            <button
              type="button"
              onClick={handleCreate}
              disabled={creating}
              className="mt-8 rounded-lg border border-gold/40 bg-gold/10 px-6 py-2.5 text-sm font-medium text-gold transition-colors hover:bg-gold/20 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {creating ? '创建中…' : '＋ 创建第一个场景'}
            </button>
          </div>
        ) : (
          <div className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
            {scenes.map((scene) => (
              <SceneCard key={scene.id} scene={scene} onChanged={refresh} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-xl border border-stage-800 bg-stage-900 p-5">
      <div className="h-5 w-20 rounded-full bg-stage-700" />
      <div className="mt-4 h-6 w-2/3 rounded bg-stage-700" />
      <div className="mt-3 h-4 w-full rounded bg-stage-800" />
      <div className="mt-2 h-4 w-5/6 rounded bg-stage-800" />
      <div className="mt-5 flex -space-x-2">
        <div className="h-7 w-7 rounded-full bg-stage-700" />
        <div className="h-7 w-7 rounded-full bg-stage-700" />
        <div className="h-7 w-7 rounded-full bg-stage-700" />
      </div>
      <div className="mt-5 border-t border-stage-800 pt-3">
        <div className="h-4 w-3/4 rounded bg-stage-800" />
      </div>
    </div>
  )
}
