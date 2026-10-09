// 补课模式摘要弹窗（§5.4.6）：有历史/未读事件时进入页面先给剧情摘要。

import { motion } from 'framer-motion'
import type { SceneSummary } from '../../types'

interface SummaryModalProps {
  summary: SceneSummary
  /** 进入现场：关闭弹窗并滚动到最新 */
  onEnterLive: () => void
  /** 查看完整记录：关闭弹窗并滚动到第一条 */
  onViewFull: () => void
  onClose: () => void
}

export function SummaryModal({ summary, onEnterLive, onViewFull, onClose }: SummaryModalProps) {
  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <motion.div
        className="relative w-full max-w-md rounded-2xl border border-gold/30 bg-stage-900 p-6 shadow-2xl"
        initial={{ opacity: 0, scale: 0.96, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 12 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
      >
        <h2 className="font-serif text-lg text-gold">📋 截至目前剧情摘要</h2>
        <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-relaxed text-stone-300">
          {summary.bullets.map((bullet, i) => (
            <li key={i}>{bullet}</li>
          ))}
        </ul>
        <div className="mt-6 flex items-center gap-2">
          <button
            type="button"
            onClick={onEnterLive}
            className="rounded-lg bg-gold px-4 py-2 text-sm font-medium text-stage-950 transition hover:brightness-110"
          >
            进入现场
          </button>
          <button
            type="button"
            onClick={onViewFull}
            className="rounded-lg border border-stage-600 px-4 py-2 text-sm text-stone-300 transition hover:bg-stage-800"
          >
            查看完整记录
          </button>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto rounded-lg px-4 py-2 text-sm text-stone-500 transition hover:text-stone-300"
          >
            关闭
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}
