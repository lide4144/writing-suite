import { useMemo } from 'react'

// 极简 markdown 渲染器（§6.4 场景文档预览）：支持 # / ## / ### 标题、- 列表、段落。
// 刻意不引入第三方 markdown 依赖。

type Block = { type: 'h1' | 'h2' | 'h3' | 'p'; text: string } | { type: 'ul'; items: string[] }

function parseBlocks(source: string): Block[] {
  const blocks: Block[] = []
  let list: string[] | null = null
  const flushList = () => {
    if (list && list.length > 0) blocks.push({ type: 'ul', items: list })
    list = null
  }
  for (const raw of source.split('\n')) {
    const line = raw.trimEnd()
    if (line.startsWith('### ')) {
      flushList()
      blocks.push({ type: 'h3', text: line.slice(4).trim() })
    } else if (line.startsWith('## ')) {
      flushList()
      blocks.push({ type: 'h2', text: line.slice(3).trim() })
    } else if (line.startsWith('# ')) {
      flushList()
      blocks.push({ type: 'h1', text: line.slice(2).trim() })
    } else if (line.startsWith('- ')) {
      list = list ?? []
      list.push(line.slice(2).trim())
    } else if (line.trim() === '') {
      flushList()
    } else {
      flushList()
      blocks.push({ type: 'p', text: line.trim() })
    }
  }
  flushList()
  return blocks
}

export function SimpleMarkdown({ source, className }: { source: string; className?: string }) {
  const blocks = useMemo(() => parseBlocks(source), [source])
  return (
    <div className={className}>
      {blocks.map((block, index) => {
        switch (block.type) {
          case 'h1':
            return (
              <h1 key={index} className="border-b border-stage-700 pb-2 font-serif text-xl font-semibold text-gold">
                {block.text}
              </h1>
            )
          case 'h2':
            return (
              <h2 key={index} className="pt-1 font-serif text-base font-semibold text-stone-100">
                {block.text}
              </h2>
            )
          case 'h3':
            return (
              <h3 key={index} className="text-sm font-semibold text-stone-200">
                {block.text}
              </h3>
            )
          case 'ul':
            return (
              <ul key={index} className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-stone-300">
                {block.items.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            )
          case 'p':
            return (
              <p key={index} className="text-sm leading-relaxed text-stone-300">
                {block.text}
              </p>
            )
        }
      })}
    </div>
  )
}
