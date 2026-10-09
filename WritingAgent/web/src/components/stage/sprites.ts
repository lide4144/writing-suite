// 像素小人图数据：16 列 × 24 行，字符映射到调色板（见 PixelActor.tsx）。
// h=头发/兜帽 s=皮肤 e=眼睛 m=嘴 t=上衣 p=裤子 o=鞋 .=透明

export type SpriteRows = string[]

/** 基础帧（站立） */
export const BASE_SPRITE: SpriteRows = [
  '.....hhhhhh.....',
  '...hhhhhhhhhh...',
  '..hhhhhhhhhhhh..',
  '..hhsssssssshh..',
  '..hhsssssssshh..',
  '..hseesssseesh..',
  '..hsssmmmmsssh..',
  '......ssss......',
  '...tttttttttt...',
  '..tttttttttttt..',
  '.tttttttttttttt.',
  '.tttttttttttttt.',
  '.tssttttttttsst.',
  '.tssttttttttsst.',
  '..tttttttttttt..',
  '..tttttttttttt..',
  '..pppppppppppp..',
  '...ppp....ppp...',
  '...ppp....ppp...',
  '...ppp....ppp...',
  '...ppp....ppp...',
  '...ppp....ppp...',
  '...ppp....ppp...',
  '..oooo....oooo..',
]

/** 走路帧：仅腿部行（17-23）不同，两腿岔开 */
export const WALK_SPRITE: SpriteRows = [
  ...BASE_SPRITE.slice(0, 17),
  '..ppp......ppp..',
  '..ppp......ppp..',
  '..ppp......ppp..',
  '..ppp......ppp..',
  '..ppp......ppp..',
  '..ppp......ppp..',
  '.ooo........ooo.',
]

/** 发型变体：按行号替换基础帧的对应行 */
export const HAIR_VARIANTS = {
  short: {} as Record<number, string>,
  long: {
    4: '.hhsssssssssshh.',
    5: '.hhseesssseeshh.',
    6: '.hhsssmmmmssshh.',
    7: '.hh...ssss...hh.',
    8: '.hh.tttttttt.hh.',
  } as Record<number, string>,
  bun: {
    0: '....hhhhhhhh....',
  } as Record<number, string>,
  hood: {
    2: '.hhhhhhhhhhhhhh.',
    3: '.hhhsssssssshhh.',
    4: '.hhsssssssssshh.',
    5: '.hhseesssseeshh.',
    6: '.hhsssmmmmssshh.',
  } as Record<number, string>,
}

export type HairStyle = keyof typeof HAIR_VARIANTS

/** 应用发型变体，得到完整像素图 */
export function applyHair(base: SpriteRows, style: HairStyle): SpriteRows {
  const patch = HAIR_VARIANTS[style]
  return base.map((row, i) => patch[i] ?? row)
}

export const SPRITE_W = 16
export const SPRITE_H = 24

/**
 * 把像素图编译成 CSS box-shadow 串（经典单元素 pixel-art 技法）。
 * palette: 字符 → 颜色；px: 单像素边长。
 */
export function buildShadow(rows: SpriteRows, palette: Record<string, string>, px: number): string {
  const parts: string[] = []
  rows.forEach((row, y) => {
    for (let x = 0; x < row.length; x++) {
      const color = palette[row[x]]
      if (color) parts.push(`${x * px}px ${y * px}px 0 0 ${color}`)
    }
  })
  return parts.join(',')
}
