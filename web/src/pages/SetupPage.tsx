import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getScene, saveSceneDoc, startScene } from '../mock/api'
import type { Scene } from '../types'
import { cn } from '../utils/cn'
import { useAppStore } from '../store/useAppStore'
import { PlaywrightChat, type PlaywrightDraft } from '../components/setup/PlaywrightChat'
import { SceneDocPreview } from '../components/setup/SceneDocPreview'

// 舞台监督（§6）：左侧与编剧对话讨论方向，右侧审阅场景文档，定稿后开演。

const STATUS_META: Record<Scene['status'], { label: string; className: string }> = {
  draft: { label: '草稿', className: 'border border-dashed border-stone-500 text-stone-400' },
  running: { label: '演出中', className: 'bg-gold/15 text-gold' },
  ended: { label: '已落幕', className: 'bg-stage-800 text-stone-500' },
}

/** 生成草稿：已有文档则「润色重现」（mock 阶段原样整理），空白则按标题模板化生成 */
function buildDraftDoc(title: string, scene: Scene, currentDoc: string): string {
  if (currentDoc.trim()) return currentDoc
  const names = scene.characters.map((c) => c.name).join('、')
  return [
    `# 场景：${title}`,
    '',
    '## 基本信息',
    '- 时间：待定',
    '- 地点：待定',
    `- 角色：${names}`,
    '',
    '## 初始状态',
    '- （待补充：每个角色带着什么心事上场）',
    '',
    '## 场景气氛',
    '（待补充：光线、声音、气味）',
    '',
    '## 背景提要',
    '（待补充：开演前需要知道的旧事）',
    '',
    '## 剧本方向',
    '（待补充：冲突如何展开，落点在哪里）',
    '',
  ].join('\n')
}

export function SetupPage() {
  const { sceneId } = useParams<{ sceneId: string }>()
  const navigate = useNavigate()
  const [scene, setScene] = useState<Scene | null | undefined>(undefined) // undefined = 加载中
  const [title, setTitle] = useState('')
  const [doc, setDoc] = useState('')
  const [reviewed, setReviewed] = useState(true)
  const [savedTick, setSavedTick] = useState(0) // 「已保存」提示
  const [draft, setDraft] = useState<PlaywrightDraft | null>(null)
  const [starting, setStarting] = useState(false)
  const setRunningScene = useAppStore((s) => s.setRunningScene)

  useEffect(() => {
    if (!sceneId) return
    let cancelled = false
    setScene(undefined)
    getScene(sceneId).then((s) => {
      if (cancelled) return
      setScene(s)
      if (s) {
        setTitle(s.title)
        setDoc(s.setupScript)
        setReviewed(true)
      }
    })
    return () => {
      cancelled = true
    }
  }, [sceneId])

  // 「已保存」提示 2 秒后消失
  useEffect(() => {
    if (savedTick === 0) return
    const t = setTimeout(() => setSavedTick(0), 2000)
    return () => clearTimeout(t)
  }, [savedTick])

  const applyToDoc = useCallback((content: string, mode: 'append' | 'replace') => {
    setDoc((prev) => {
      if (mode === 'replace') return content
      // 编剧的文字回复：以「编剧笔记」小节沉淀到文档末尾
      const bullet = `- ${content}`
      return prev.includes('## 编剧笔记')
        ? `${prev.trimEnd()}\n${bullet}\n`
        : `${prev.trimEnd()}\n\n## 编剧笔记\n${bullet}\n`
    })
    setReviewed(false)
  }, [])

  const handleManualEdit = useCallback((next: string) => {
    setDoc(next)
    setReviewed(false)
  }, [])

  const handleSave = async () => {
    if (!scene) return
    await saveSceneDoc(scene.id, doc, title)
    setReviewed(true)
    setSavedTick(Date.now())
  }

  const handleDraft = () => {
    if (!scene) return
    const draftDoc = buildDraftDoc(title, scene, doc)
    setDoc(draftDoc)
    setReviewed(false)
    setDraft((prev) => ({ doc: draftDoc, seq: (prev?.seq ?? 0) + 1 }))
  }

  const handleStart = async () => {
    if (!scene || starting) return
    setStarting(true)
    await saveSceneDoc(scene.id, doc, title)
    await startScene(scene.id)
    setRunningScene(scene.id) // 导航栏「运行中」指示器指向本场景（§8.3）
    navigate(`/stage/${scene.id}/watch`)
  }

  if (scene === undefined) {
    return (
      <div className="flex h-screen items-center justify-center bg-stage-950 text-sm text-stone-500">
        正在准备后台…
      </div>
    )
  }

  if (scene === null) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 bg-stage-950">
        <p className="font-serif text-2xl text-stone-300">这个舞台不存在</p>
        <p className="text-sm text-stone-500">也许它从未搭起，或者已经拆台。</p>
        <Link to="/" className="text-sm text-gold hover:underline">
          ← 返回场景画廊
        </Link>
      </div>
    )
  }

  const meta = STATUS_META[scene.status]

  return (
    <div className="flex h-screen flex-col bg-stage-950">
      {/* 顶栏：返回 / 场景名称 / 保存 / 状态徽章 */}
      <header className="flex items-center gap-4 border-b border-stage-700 px-5 py-3">
        <Link to="/" className="shrink-0 text-sm text-stone-400 hover:text-gold">
          ← 返回场景画廊
        </Link>
        <div className="h-4 w-px bg-stage-700" />
        <label className="flex min-w-0 flex-1 items-center gap-2">
          <span className="shrink-0 text-sm text-stone-500">场景名称</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-72 rounded bg-stage-800 px-2.5 py-1.5 text-sm text-stone-100 outline-none focus:ring-1 focus:ring-gold"
          />
        </label>
        {savedTick !== 0 && <span className="text-xs text-gold">已保存 ✓</span>}
        <button
          onClick={() => void handleSave()}
          className="shrink-0 rounded border border-stage-600 px-3 py-1.5 text-sm text-stone-300 hover:border-gold hover:text-gold"
        >
          💾 保存
        </button>
        <span className={cn('shrink-0 rounded-full px-2.5 py-1 text-xs', meta.className)}>{meta.label}</span>
      </header>

      {/* 双栏：编剧对话 / 文档预览 */}
      <main className="flex min-h-0 flex-1 gap-4 p-4">
        <div className="w-[400px] shrink-0 xl:w-[440px]">
          <PlaywrightChat key={scene.id} draft={draft} onApplyToDoc={applyToDoc} />
        </div>
        <div className="min-w-0 flex-1">
          <SceneDocPreview doc={doc} reviewed={reviewed} onManualEdit={handleManualEdit} />
        </div>
      </main>

      {/* 底部操作 */}
      <footer className="flex items-center gap-3 border-t border-stage-700 px-5 py-3">
        <button
          onClick={handleDraft}
          className="rounded border border-gold/60 px-4 py-2 text-sm text-gold transition-colors hover:bg-gold/10"
        >
          📋 生成草稿
        </button>
        <button
          onClick={() => void handleStart()}
          disabled={starting}
          className="rounded bg-gold px-5 py-2 text-sm font-medium text-stage-950 transition-opacity disabled:opacity-50"
        >
          {starting ? '⏳ 演出中…' : '🎬 开演 →'}
        </button>
        <span className="text-xs text-stone-600">开演会将场景文档推送给 GM 与角色，并带你到观众席。</span>
      </footer>
    </div>
  )
}
