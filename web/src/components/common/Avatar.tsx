import { cn } from '../../utils/cn'

interface AvatarProps {
  name: string
  color: string
  size?: number // px
  className?: string
}

/** 角色头像：mock 阶段以角色主题色 + 名字首字渲染 */
export function Avatar({ name, color, size = 32, className }: AvatarProps) {
  return (
    <span
      className={cn('inline-flex shrink-0 items-center justify-center rounded-full font-medium text-stage-950 select-none', className)}
      style={{
        width: size,
        height: size,
        backgroundColor: color,
        fontSize: size * 0.44,
      }}
      aria-label={name}
    >
      {name.slice(0, 1)}
    </span>
  )
}
