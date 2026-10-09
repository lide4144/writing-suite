// 像素小人：CSS box-shadow 单元素绘制 16×24 像素图，纯 CSS 动画。
// pose: idle（呼吸）/ talk（弹跳）/ walk（两帧交替 + 位移由父级 transition 完成）。
// facing 用内层 scaleX(-1) 翻转；呼吸/弹跳动画放在外层避免 transform 冲突。

import { useMemo } from 'react'
import { applyHair, BASE_SPRITE, buildShadow, SPRITE_H, SPRITE_W, WALK_SPRITE } from './sprites'
import { lookOf } from './pixelActors'
import { cn } from '../../utils/cn'

export type ActorPose = 'idle' | 'talk' | 'walk' | 'emote'

const PX = 3 // 单像素边长（px），整体 48×72

interface PixelActorProps {
  characterId: string
  name: string
  pose: ActorPose
  facing: 'left' | 'right'
  emote: string | null
  onEnter?: (characterId: string, rect: DOMRect) => void
  onLeave?: () => void
}

function paletteOf(look: ReturnType<typeof lookOf>): Record<string, string> {
  return {
    h: look.hair,
    s: look.skin,
    e: '#26262e',
    m: '#b46a5a',
    t: look.top,
    p: look.pants,
    o: '#26262e',
  }
}

export function PixelActor({ characterId, name, pose, facing, emote, onEnter, onLeave }: PixelActorProps) {
  const look = lookOf(characterId)

  // 每个形象编译一次 box-shadow（含发型变体）
  const { idleShadow, walkShadow } = useMemo(() => {
    const palette = paletteOf(look)
    const idle = applyHair(BASE_SPRITE, look.hairStyle)
    const walk = applyHair(WALK_SPRITE, look.hairStyle)
    return {
      idleShadow: buildShadow(idle, palette, PX),
      walkShadow: buildShadow(walk, palette, PX),
    }
  }, [look])

  const walking = pose === 'walk'

  return (
    <div
      role="img"
      aria-label={name}
      className={cn('relative cursor-pointer', pose === 'idle' && 'pixel-idle', (pose === 'talk' || pose === 'emote') && 'pixel-talk')}
      style={{ width: SPRITE_W * PX, height: SPRITE_H * PX, imageRendering: 'pixelated' }}
      onMouseEnter={(e) => onEnter?.(characterId, e.currentTarget.getBoundingClientRect())}
      onMouseLeave={onLeave}
    >
      <div style={{ transform: facing === 'left' ? 'scaleX(-1)' : undefined }}>
        {/* 站立帧 */}
        <div style={{ width: PX, height: PX, boxShadow: idleShadow }} />
        {/* 走路帧：叠加，steps(1) 交替显隐 */}
        {walking && (
          <div className="pixel-walk-frame absolute left-0 top-0" style={{ width: PX, height: PX, boxShadow: walkShadow }} />
        )}
        {/* 配饰 */}
        {look.accessory === 'notebook' && (
          <div
            className="absolute"
            style={{ left: 12 * PX, top: 11 * PX, width: 4 * PX, height: 5 * PX, backgroundColor: '#7a5a3a', boxShadow: `inset ${PX}px 0 0 #d8cbb0` }}
          />
        )}
        {look.accessory === 'mug' && (
          <div
            className="absolute"
            style={{ left: 0, top: 12 * PX, width: 3 * PX, height: 3 * PX, backgroundColor: '#d8d4cc', boxShadow: `${3 * PX}px ${PX}px 0 -1px #d8d4cc` }}
          />
        )}
        {look.accessory === 'glasses' && (
          <>
            <div className="absolute border border-[#26262e]" style={{ left: 4 * PX, top: 5 * PX, width: 3 * PX, height: 2 * PX }} />
            <div className="absolute border border-[#26262e]" style={{ left: 10 * PX, top: 5 * PX, width: 3 * PX, height: 2 * PX }} />
            <div className="absolute bg-[#26262e]" style={{ left: 7 * PX, top: 5 * PX + 1, width: 3 * PX, height: 1 }} />
          </>
        )}
      </div>
      {/* 情绪符号 */}
      {emote && (
        <span className="absolute -top-4 left-1/2 -translate-x-1/2">
          <span className="pixel-bubble-pop block text-xs leading-none">{emote}</span>
        </span>
      )}
    </div>
  )
}
