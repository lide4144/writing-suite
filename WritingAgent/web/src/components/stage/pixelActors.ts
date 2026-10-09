// 角色像素形象参数表：发色/肤色/衣服色（=角色主题色）/发型/标志性配饰。
// 未登记的角色用 DEFAULT_LOOK（灰色小人）。

import type { HairStyle } from './sprites'

export type Accessory = 'notebook' | 'mug' | 'glasses' | null

export interface PixelLook {
  hair: string
  skin: string
  top: string
  pants: string
  hairStyle: HairStyle
  accessory: Accessory
}

export const DEFAULT_LOOK: PixelLook = {
  hair: '#4a4a52',
  skin: '#e8c0a0',
  top: '#8a8a96',
  pants: '#3a3f4a',
  hairStyle: 'short',
  accessory: null,
}

export const PIXEL_LOOKS: Record<string, PixelLook> = {
  'char-lin-wan': {
    hair: '#4a3728',
    skin: '#f0c8a8',
    top: '#e8927c',
    pants: '#3a3f4a',
    hairStyle: 'long',
    accessory: 'notebook',
  },
  'char-shen-yu': {
    hair: '#2a2a30',
    skin: '#ecc09c',
    top: '#6a9bd8',
    pants: '#2e3440',
    hairStyle: 'short',
    accessory: 'mug',
  },
  'char-gu-yao': {
    hair: '#4e6b3f', // 兜帽色
    skin: '#f0c8a8',
    top: '#8fbf6a',
    pants: '#3a3f4a',
    hairStyle: 'hood',
    accessory: null,
  },
  'char-su-li': {
    hair: '#3a2a4a',
    skin: '#f0c8a8',
    top: '#c987d6',
    pants: '#2e3440',
    hairStyle: 'bun',
    accessory: 'glasses',
  },
}

export function lookOf(characterId: string): PixelLook {
  return PIXEL_LOOKS[characterId] ?? DEFAULT_LOOK
}
