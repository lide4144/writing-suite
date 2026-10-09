import { useState } from 'react'
import { cn } from '../../utils/cn'
import { SimpleMarkdown } from './SimpleMarkdown'

// 场景文档预览区（§6.4 右侧）：渲染结构化场景文档，可切换为编辑模式。
// 手动修改后由父组件标记「未审阅」。

interface SceneDocPreviewProps {
  doc: string
  reviewed: boolean
  onManualEdit: (doc: string) => void
}

export function SceneDocPreview({ doc, reviewed, onManualEdit }: SceneDocPreviewProps) {
  const [editing, setEditing] = useState(false)

  return (
    <div className="flex h-full flex-col rounded-lg border border-stage-700 bg-stage-900">
      <header className="flex items-center justify-between border-b border-stage-700 px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-stone-100">场景文档</span>
          <span
            className={cn(
              'rounded-full px-2 py-0.5 text-xs',
              reviewed ? 'bg-stage-800 text-stone-500' : 'bg-gold/15 text-gold',
            )}
          >
            {reviewed ? '已审阅' : '未审阅'}
          </span>
        </div>
        <button
          onClick={() => setEditing((v) => !v)}
          className="rounded border border-stage-600 px-2.5 py-1 text-xs text-stone-400 hover:border-gold hover:text-gold"
        >
          {editing ? '完成' : '✏️ 编辑'}
        </button>
      </header>

      {editing ? (
        <textarea
          value={doc}
          onChange={(e) => onManualEdit(e.target.value)}
          placeholder="用 markdown 编写场景文档：# 标题、## 小节、- 列表…"
          className="flex-1 resize-none bg-stage-950/60 p-4 font-mono text-sm leading-relaxed text-stone-200 outline-none placeholder:text-stone-600"
        />
      ) : (
        <div className="flex-1 overflow-y-auto p-5">
          {doc.trim() ? (
            <SimpleMarkdown source={doc} className="space-y-3" />
          ) : (
            <p className="text-sm text-stone-500">
              文档还是空白。先在左侧和编剧讨论方向，或点下方「📋 生成草稿」。
            </p>
          )}
        </div>
      )}
    </div>
  )
}
