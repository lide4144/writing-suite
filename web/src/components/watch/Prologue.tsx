// 场景序幕（§5.4.5）：加载期间屏幕中央淡入的叙事开场白卡片。
// 内容 = 场景标题 + 时间地点 + 时间线前几条 env/action 消息拼成的叙事段落。

import { motion } from 'framer-motion'
import type { Message, Scene } from '../../types'
import { formatDate } from '../../utils/time'

interface PrologueProps {
  scene: Scene
  messages: Message[]
}

const MAX_NARRATIVE_LINES = 4

export function Prologue({ scene, messages }: PrologueProps) {
  // 「场景：xxx。下午两点，雨刚停。」作为时间地点行
  const opening = messages.find((m) => m.type === 'scene_change')
  const openingLine = opening ? opening.content.replace(/^场景：/, '') : null

  const narrative = messages
    .filter((m) => m.type === 'env' || m.type === 'action')
    .slice(0, MAX_NARRATIVE_LINES)
    .map((m) => m.content)
  if (narrative.length === 0 && scene.description) narrative.push(scene.description)

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center bg-stage-950/90 backdrop-blur-sm"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.7 } }}
    >
      <motion.div
        className="w-full max-w-xl rounded-2xl border border-stage-700 bg-stage-900/80 px-10 py-12 shadow-2xl"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0, transition: { duration: 0.8, ease: 'easeOut' } }}
        exit={{ opacity: 0, y: -12 }}
      >
        <div className="mb-6 flex items-center justify-between text-xs tracking-[0.3em] text-stone-500">
          <span>场 景 序 幕</span>
          {scene.status === 'running' && (
            <span className="flex items-center gap-1.5 tracking-normal text-gold">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-gold" />
              正在直播中
            </span>
          )}
        </div>
        <h1 className="font-serif text-3xl text-stone-100">{scene.title}</h1>
        <p className="mt-3 text-sm text-stone-400">
          {formatDate(scene.startedAt ?? scene.lastActivityAt)}
          {openingLine ? ` · ${openingLine}` : ''}
        </p>
        <div className="mt-8 space-y-4 font-serif leading-relaxed text-stone-300">
          {narrative.map((line, i) => (
            <motion.p
              key={i}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1, transition: { delay: 0.3 + i * 0.25, duration: 0.5 } }}
            >
              {line}
            </motion.p>
          ))}
        </div>
      </motion.div>
    </motion.div>
  )
}
