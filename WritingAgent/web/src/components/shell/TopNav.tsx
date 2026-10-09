import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { SCENES } from '../../mock/data'
import { useAppStore } from '../../store/useAppStore'
import { NotificationBell } from './NotificationBell'

/** 顶部热区高度（px）：鼠标进入屏幕顶部该区域时导航栏滑出（§3.1） */
const HOT_ZONE = 60

// 顶部导航栏：默认隐藏，鼠标移至顶部边缘滑出，离开后收回；半透明毛玻璃，不遮挡内容。
export function TopNav() {
  const [visible, setVisible] = useState(false)
  const navRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      // 鼠标在导航栏（含展开的通知下拉）内部时保持可见，离开后收回
      const inNav = navRef.current?.contains(e.target as Node) ?? false
      setVisible(e.clientY <= HOT_ZONE || inNav)
    }
    window.addEventListener('mousemove', onMouseMove)
    return () => window.removeEventListener('mousemove', onMouseMove)
  }, [])

  const runningSceneId = useAppStore((s) => s.runningSceneId)
  const runningScene = runningSceneId ? SCENES.find((s) => s.id === runningSceneId) ?? null : null

  return (
    <motion.header
      ref={navRef}
      initial={false}
      animate={{ y: visible ? 0 : '-100%' }}
      transition={{ type: 'spring', stiffness: 320, damping: 32 }}
      className="fixed inset-x-0 top-0 z-50 border-b border-stage-700/60 bg-stage-950/70 backdrop-blur-md"
    >
      <div className="relative mx-auto flex h-14 max-w-[1600px] items-center justify-between px-6">
        {/* 左侧：站点标志 */}
        <Link to="/" className="flex items-center gap-2 text-stone-200 transition-colors hover:text-gold">
          <span className="text-lg leading-none">🎭</span>
          <span className="text-sm font-semibold tracking-[0.3em]">独立角色舞台</span>
        </Link>

        {/* 中部：运行中场景指示器 */}
        {runningScene && (
          <Link
            to={`/stage/${runningScene.id}/watch`}
            className="absolute left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-full border border-gold/30 bg-gold/10 px-4 py-1 text-xs text-gold transition-colors hover:bg-gold/20"
            title="进入观众席"
          >
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-gold opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-gold" />
            </span>
            <span className="max-w-64 truncate">
              场景 #{runningScene.id.replace('scene-', '')}：{runningScene.title}
            </span>
            <span className="text-stone-400">运行中 ⏵</span>
          </Link>
        )}

        {/* 右侧：通知铃铛 */}
        <NotificationBell />
      </div>
    </motion.header>
  )
}
