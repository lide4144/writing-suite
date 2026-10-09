// 💭 内心独白入口（§8.2）：活动流默认只显示对外表现，
// 点击后在当前位置就地展开内心独白浮层（角色主题色左边框），再点收起。

import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

interface InnerThoughtToggleProps {
  thought: string
  color: string
  name: string
}

export function InnerThoughtToggle({ thought, color, name }: InnerThoughtToggleProps) {
  const [open, setOpen] = useState(false)

  return (
    <div className="mt-2">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="rounded-full bg-black/30 px-2.5 py-1 text-xs text-stone-400 transition-colors hover:bg-black/50 hover:text-stone-200"
        >
          💭 {open ? '收起内心' : '内心'}
        </button>
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            className="overflow-hidden"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
          >
            <div
              className="mt-2 rounded-r-lg border-l-2 bg-stage-950/70 px-3 py-2"
              style={{ borderLeftColor: color }}
            >
              <div className="mb-1 text-xs" style={{ color }}>
                {name}的内心
              </div>
              <p className="font-serif text-sm leading-relaxed text-stone-300">{thought}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
